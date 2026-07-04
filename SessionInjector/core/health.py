"""Session Health Score — the portfolio differentiator.

Instead of a binary works / doesn't-work verdict, we compute a 0-100 score
from several weighted signals so the result is explainable and observable:

    * essential cookies present (weight 35)
    * freshness — how few cookies are expired (weight 20)
    * attribute hygiene — Secure / HttpOnly / SameSite set where expected (15)
    * consistency — cookies concentrated on the target domain (10)
    * live browser test result (weight 20)

Each factor returns a 0..1 ratio; the weighted sum is scaled to 0-100 and the
per-factor breakdown is returned for display.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..config.profiles import ServiceProfile
from ..cookies.models import Cookie, SessionStatus, ValidationResult

WEIGHTS = {
    "essential": 35,
    "freshness": 20,
    "attributes": 15,
    "consistency": 10,
    "browser": 20,
}


@dataclass
class HealthScore:
    service: str
    score: int = 0
    factors: dict[str, float] = field(default_factory=dict)  # factor -> 0..1
    contributions: dict[str, float] = field(default_factory=dict)  # factor -> points
    notes: list[str] = field(default_factory=list)

    @property
    def stars(self) -> str:
        filled = round(self.score / 20)
        return "★" * filled + "☆" * (5 - filled)

    @property
    def grade(self) -> str:
        if self.score >= 85:
            return "Functional"
        if self.score >= 60:
            return "Likely functional"
        if self.score >= 35:
            return "Weak"
        return "Broken"

    def as_dict(self) -> dict:
        return {
            "service": self.service,
            "score": self.score,
            "stars": self.stars,
            "grade": self.grade,
            "factors": self.factors,
            "contributions": self.contributions,
            "notes": self.notes,
        }


def _essential_factor(live: list[Cookie], profile: ServiceProfile) -> float:
    if not profile.required_cookies:
        return 1.0
    present = {c.name for c in live}
    have = sum(1 for name in profile.required_cookies if name in present)
    return have / len(profile.required_cookies)


def _freshness_factor(scoped: list[Cookie], now: float) -> float:
    if not scoped:
        return 0.0
    live = sum(1 for c in scoped if not c.is_expired(now))
    return live / len(scoped)


def _attribute_factor(live: list[Cookie]) -> float:
    """Reward sessions whose sensitive cookies carry the right attributes."""
    if not live:
        return 0.0
    total = 0.0
    for c in live:
        score = 0.0
        score += 1.0 if c.secure else 0.0
        score += 1.0 if c.http_only else 0.0
        score += 1.0 if c.same_site is not None else 0.0
        total += score / 3.0
    return total / len(live)


def _consistency_factor(scoped: list[Cookie], all_cookies: list[Cookie]) -> float:
    """How concentrated the set is on the target domain (0..1)."""
    if not all_cookies:
        return 0.0
    return len(scoped) / len(all_cookies)


def _browser_factor(validation: ValidationResult | None) -> tuple[float, bool]:
    """Return (factor, counted). ``counted`` is False when no test ran."""
    if validation is None:
        return 0.0, False
    mapping = {
        SessionStatus.FUNCTIONAL: 1.0,
        SessionStatus.UNKNOWN: 0.5,
        SessionStatus.INCOMPLETE: 0.25,
        SessionStatus.EXPIRED: 0.0,
        SessionStatus.INVALID: 0.0,
    }
    return mapping.get(validation.status, 0.0), True


def compute_health(
    cookies: list[Cookie],
    profile: ServiceProfile,
    validation: ValidationResult | None = None,
    now: float | None = None,
) -> HealthScore:
    now = now if now is not None else time.time()
    scoped = [c for c in cookies if profile.owns(c.registrable_domain)]
    live = [c for c in scoped if not c.is_expired(now)]

    factors = {
        "essential": _essential_factor(live, profile),
        "freshness": _freshness_factor(scoped, now),
        "attributes": _attribute_factor(live),
        "consistency": _consistency_factor(scoped, cookies),
    }
    browser_factor, browser_counted = _browser_factor(validation)
    factors["browser"] = browser_factor

    # If no browser test ran, redistribute its weight over the other factors
    # so the score still tops out at 100.
    active_weights = dict(WEIGHTS)
    if not browser_counted:
        del active_weights["browser"]
        factors.pop("browser", None)

    total_weight = sum(active_weights.values())
    contributions: dict[str, float] = {}
    total_points = 0.0
    for name, weight in active_weights.items():
        pts = factors[name] * (weight / total_weight) * 100
        contributions[name] = round(pts, 1)
        total_points += pts

    result = HealthScore(
        service=profile.key,
        score=int(round(total_points)),
        factors={k: round(v, 3) for k, v in factors.items()},
        contributions=contributions,
    )

    # Human-readable notes for the weakest factors.
    for name in sorted(factors, key=lambda n: factors[n]):
        if factors[name] < 0.5:
            result.notes.append(f"Low {name} score ({factors[name]:.0%}).")
    if not browser_counted:
        result.notes.append("Browser test not run — score is local-only.")
    return result
