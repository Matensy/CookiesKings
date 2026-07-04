"""Session Tester.

Runs the full validation flow across one or more services and aggregates the
results into a dashboard-friendly summary, including the Health Score for each.
Reuses a single browser instance across all services.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from ..config.profiles import PROFILES, ServiceProfile, profile_for_domain
from ..cookies.models import Cookie, ValidationResult
from ..browser.manager import BrowserManager, BrowserUnavailable, playwright_available
from ..browser.validator import validate
from .health import HealthScore, compute_health
from .logging_config import get_logger

logger = get_logger()


@dataclass
class ServiceOutcome:
    profile: ServiceProfile
    validation: ValidationResult
    health: HealthScore


@dataclass
class TestSession:
    outcomes: list[ServiceOutcome] = field(default_factory=list)
    used_browser: bool = False

    def best(self) -> ServiceOutcome | None:
        return max(self.outcomes, key=lambda o: o.health.score, default=None)


def _detect_services(cookies: list[Cookie]) -> list[ServiceProfile]:
    """Pick the service profiles that the given cookies actually touch."""
    found: dict[str, ServiceProfile] = {}
    for c in cookies:
        profile = profile_for_domain(c.registrable_domain)
        if profile:
            found[profile.key] = profile
    return list(found.values())


def test_sessions(
    cookies: list[Cookie],
    services: Iterable[str] | None = None,
    use_browser: bool = True,
    headless: bool = True,
) -> TestSession:
    """Validate and score the cookies against the relevant services.

    ``services`` restricts the run to specific profile keys; when omitted, the
    services are auto-detected from the cookies. The browser is launched once
    and shared, and gracefully skipped if Playwright is unavailable.
    """
    if services:
        profiles = [PROFILES[s] for s in services if s in PROFILES]
    else:
        profiles = _detect_services(cookies)

    if not profiles:
        logger.warning("No known service profiles matched the imported cookies.")
        return TestSession()

    session = TestSession()
    manager: BrowserManager | None = None

    want_browser = use_browser and playwright_available()
    if use_browser and not want_browser:
        logger.warning("Playwright unavailable — running local-only validation.")

    try:
        if want_browser:
            try:
                manager = BrowserManager(headless=headless).start()
                session.used_browser = True
            except BrowserUnavailable as exc:
                logger.warning("Browser could not start (%s); local-only.", exc)
                manager = None

        for profile in profiles:
            logger.info("Validating %s session…", profile.label)
            validation = validate(cookies, profile, manager=manager)
            health = compute_health(
                cookies, profile, validation if manager else None
            )
            logger.info(
                "%s: %s | health %d/100 %s",
                profile.label, validation.status.value, health.score, health.stars,
            )
            session.outcomes.append(ServiceOutcome(profile, validation, health))
    finally:
        if manager is not None:
            manager.stop()

    return session
