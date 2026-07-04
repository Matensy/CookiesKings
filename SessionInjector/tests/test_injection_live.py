"""Live injection test — runs only when Playwright + Chromium are available.

This is the test that would have caught the __Host- regression: it injects
cookies into a REAL browser context and asserts they actually land in the
store (a shape Playwright silently rejects would fail here, not in a unit test).
Skipped automatically in environments without a browser.
"""
from __future__ import annotations

import os

import pytest

from SessionInjector.browser.injector import inject_cookies
from SessionInjector.cookies.models import Cookie

FUTURE = 4_102_444_800.0

playwright = pytest.importorskip("playwright.sync_api")


def _launch(pw):
    """Launch Chromium, honouring a pre-installed binary if one is set."""
    exe = os.environ.get("SI_CHROME_PATH")
    kwargs = {"headless": True}
    if exe:
        kwargs["executable_path"] = exe
    try:
        return pw.chromium.launch(**kwargs)
    except Exception as exc:  # no browser binary present
        pytest.skip(f"Chromium not available: {exc}")


def test_host_and_secure_cookies_actually_land():
    cookies = [
        Cookie("__Host-1PLSID", "v", "accounts.google.com", "/", FUTURE, True, True),
        Cookie("__Host-GAPS", "v", "accounts.google.com", "/", FUTURE, True, True),
        Cookie("__Secure-3PSID", "v", ".google.com", "/", FUTURE, True, True),
        Cookie("SID", "v", ".google.com", "/", FUTURE, True, True),
    ]
    with playwright.sync_playwright() as pw:
        browser = _launch(pw)
        context = browser.new_context()
        try:
            present = inject_cookies(context, cookies)
            stored = {c["name"] for c in context.cookies()}
        finally:
            context.close()
            browser.close()

    # Every cookie — including the __Host- ones — must be in the store.
    for c in cookies:
        assert c.name in stored, f"{c.name} was dropped by the browser"
    assert present == len(cookies)
