"""Session Validator.

Layered validation of a cookie set against a service profile. The cheaper,
offline levels run first and can short-circuit before ever launching a browser:

    Level 1  LOCAL     - any usable (non-expired) cookies for the service?
    Level 2  DOMAIN    - do we actually hold cookies for the target domain?
    Level 3  REQUIRED  - are the essential session cookies present?
    Level 4  BROWSER   - inject into Chromium, navigate, inspect the result.
"""
from __future__ import annotations

import time

from ..config.profiles import ServiceProfile
from ..cookies.models import (
    Cookie,
    SessionStatus,
    ValidationLevel,
    ValidationResult,
)
from .manager import BrowserManager, BrowserUnavailable


def _cookies_for_service(cookies: list[Cookie], profile: ServiceProfile) -> list[Cookie]:
    return [c for c in cookies if profile.owns(c.registrable_domain)]


def validate_local(
    cookies: list[Cookie],
    profile: ServiceProfile,
    now: float | None = None,
) -> ValidationResult:
    """Run levels 1-3 (fully offline)."""
    now = now if now is not None else time.time()
    result = ValidationResult(service=profile.key)

    scoped = _cookies_for_service(cookies, profile)

    # Level 1 - local: is there anything non-expired at all?
    result.reached_level = ValidationLevel.LOCAL
    live = [c for c in scoped if not c.is_expired(now)]
    if not scoped:
        result.status = SessionStatus.INVALID
        result.notes.append("No cookies for this service's domain.")
        return result
    if not live:
        result.status = SessionStatus.EXPIRED
        result.notes.append("All cookies for this service are expired.")
        return result

    # Level 2 - domain confirmed (we have live, in-domain cookies).
    result.reached_level = ValidationLevel.DOMAIN

    # Level 3 - required cookies.
    result.reached_level = ValidationLevel.REQUIRED
    present = {c.name for c in live}
    missing = [name for name in profile.required_cookies if name not in present]
    result.missing_required = missing
    if profile.required_cookies:
        threshold = len(profile.required_cookies) / 2
        if len(missing) > threshold:
            result.status = SessionStatus.INCOMPLETE
            result.notes.append(
                f"Missing {len(missing)}/{len(profile.required_cookies)} "
                f"required cookies: {', '.join(missing)}"
            )
            return result

    result.status = SessionStatus.UNKNOWN
    result.notes.append("Local checks passed; browser test needed to confirm.")
    return result


def validate_browser(
    cookies: list[Cookie],
    profile: ServiceProfile,
    manager: BrowserManager,
    timeout_ms: int = 20_000,
) -> ValidationResult:
    """Level 4 - the real browser round-trip.

    Injects the cookies, navigates to the service's test URL, and decides
    logged-in vs signed-out from the final URL and (if configured) a DOM
    selector. Assumes ``manager`` is already started.
    """
    result = ValidationResult(service=profile.key)
    result.reached_level = ValidationLevel.BROWSER

    scoped = _cookies_for_service(cookies, profile)
    if not scoped:
        result.status = SessionStatus.INVALID
        result.notes.append("No cookies for this service's domain.")
        return result

    context = None
    try:
        context = manager.new_context(scoped)
        page = context.new_page()
        page.goto(profile.test_url, wait_until="domcontentloaded", timeout=timeout_ms)
        try:
            page.wait_for_load_state("networkidle", timeout=5_000)
        except Exception:
            pass  # networkidle is best-effort

        final_url = page.url
        result.final_url = final_url

        # URL heuristic.
        redirected = any(m in final_url for m in profile.signed_out_url_markers)

        # DOM heuristic (more robust than URL alone).
        logged_in_dom = None
        if profile.logged_in_selector:
            try:
                logged_in_dom = page.query_selector(profile.logged_in_selector) is not None
            except Exception:
                logged_in_dom = None

        if logged_in_dom is True:
            result.logged_in = True
            result.status = SessionStatus.FUNCTIONAL
        elif redirected:
            result.logged_in = False
            result.status = SessionStatus.INVALID
            result.notes.append(f"Redirected to a sign-in page: {final_url}")
        elif logged_in_dom is False:
            result.logged_in = False
            result.status = SessionStatus.INVALID
            result.notes.append("Logged-in indicator not found in the page.")
        else:
            # No redirect and we couldn't read the DOM marker -> optimistic.
            result.logged_in = True
            result.status = SessionStatus.FUNCTIONAL
            result.notes.append("No sign-in redirect detected.")

        return result
    except BrowserUnavailable:
        raise
    except Exception as exc:
        result.status = SessionStatus.UNKNOWN
        result.notes.append(f"Browser test error: {exc}")
        return result
    finally:
        if context is not None:
            try:
                context.close()
            except Exception:
                pass


def validate(
    cookies: list[Cookie],
    profile: ServiceProfile,
    manager: BrowserManager | None = None,
    now: float | None = None,
) -> ValidationResult:
    """Full validation: local levels, escalating to a browser test when needed.

    If local checks already settle the verdict (no cookies, all expired, or too
    many required cookies missing), the browser is never launched. When a
    ``manager`` is supplied and locals are inconclusive, level 4 runs.
    """
    local = validate_local(cookies, profile, now=now)
    if local.status in (
        SessionStatus.INVALID,
        SessionStatus.EXPIRED,
        SessionStatus.INCOMPLETE,
    ):
        return local
    if manager is None:
        return local  # inconclusive without a browser
    return validate_browser(cookies, profile, manager)
