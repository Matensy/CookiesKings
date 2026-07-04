"""Cookie Injector.

Writes cookies into a Playwright ``BrowserContext`` *before* navigation, using
``context.add_cookies()``. This does not touch the page HTML or run JavaScript
— it populates the browser's own cookie store, exactly as the browser would
after a real login. The server then decides whether to honour the session.

Correctness details that make or break a session restore:

  * ``__Host-`` cookies **must** be host-only (no Domain attribute) and Secure
    with Path=/. If injected with a domain they are silently dropped by
    Chromium, which quietly breaks the session. We inject them via ``url``.
  * ``__Secure-`` cookies **must** carry Secure=true or Chromium drops them; we
    force it on when the name demands it.
"""
from __future__ import annotations

from ..cookies.models import Cookie


def _cookie_payload(cookie: Cookie) -> dict:
    """Build the Playwright dict for one cookie, honouring prefix rules."""
    name = cookie.name
    host = cookie.registrable_domain  # domain without a leading dot

    if name.startswith("__Host-"):
        # Host-only + Secure + Path=/. Use `url` so Chromium sets it host-only;
        # never send a `domain` for these or the cookie is rejected.
        data = {
            "name": name,
            "value": cookie.value,
            "url": f"https://{host}/",
            "path": "/",
            "secure": True,
            "httpOnly": cookie.http_only,
        }
    else:
        data = cookie.to_playwright()
        if name.startswith("__Secure-"):
            data["secure"] = True  # required, or Chromium drops it

    if not cookie.is_session_cookie:
        data["expires"] = float(cookie.expires)
    return data


def to_playwright_cookies(cookies: list[Cookie]) -> list[dict]:
    """Serialise Cookie objects, skipping ones Playwright would reject."""
    out: list[dict] = []
    for cookie in cookies:
        if not cookie.domain:
            continue
        out.append(_cookie_payload(cookie))
    return out


def inject_cookies(context, cookies: list[Cookie], logger=None) -> int:
    """Inject cookies into a live Playwright context.

    Returns how many cookies are actually present in the store afterwards
    (verified by reading them back), which is the number that matters — a
    cookie Playwright "accepts" can still be dropped by Chromium's rules. When
    a ``logger`` is given, reports how many stuck vs. how many were dropped.
    """
    payload = to_playwright_cookies(cookies)
    if not payload:
        return 0

    try:
        context.add_cookies(payload)
    except Exception:
        # Fall back to resilient per-cookie injection.
        for single in payload:
            try:
                context.add_cookies([single])
            except Exception:
                if logger:
                    logger.warning("Cookie rejeitado na injeção: %s", single.get("name"))
                continue

    # Verify what actually landed in the store.
    try:
        present = len(context.cookies())
    except Exception:
        present = len(payload)

    if logger:
        dropped = len(payload) - present
        if dropped > 0:
            logger.warning("Injetados %d cookies; %d não foram aceitos pelo navegador.",
                           present, dropped)
        else:
            logger.info("Injetados %d cookies (todos aceitos).", present)
    return present
