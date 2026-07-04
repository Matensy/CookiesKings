"""Cookie Injector.

Writes cookies into a Playwright ``BrowserContext`` *before* navigation, using
``context.add_cookies()``. This does not touch the page HTML or run JavaScript
— it populates the browser's own cookie store, exactly as the browser would
after a real login. The server then decides whether to honour the session.
"""
from __future__ import annotations

from ..cookies.models import Cookie


def to_playwright_cookies(cookies: list[Cookie]) -> list[dict]:
    """Serialise Cookie objects, skipping ones Playwright would reject.

    Playwright requires either a ``url`` or a ``domain``+``path`` pair. We
    always provide domain+path, so we only drop cookies with an empty domain.
    """
    out: list[dict] = []
    for cookie in cookies:
        if not cookie.domain:
            continue
        out.append(cookie.to_playwright())
    return out


def inject_cookies(context, cookies: list[Cookie]) -> int:
    """Inject cookies into a live Playwright context.

    Returns the number of cookies actually handed to the browser. Playwright
    can reject a whole batch if a single cookie is malformed, so on a batch
    failure we retry one-by-one and keep the ones that stick.
    """
    payload = to_playwright_cookies(cookies)
    if not payload:
        return 0

    try:
        context.add_cookies(payload)
        return len(payload)
    except Exception:
        # Fall back to resilient per-cookie injection.
        accepted = 0
        for single in payload:
            try:
                context.add_cookies([single])
                accepted += 1
            except Exception:
                continue
        return accepted
