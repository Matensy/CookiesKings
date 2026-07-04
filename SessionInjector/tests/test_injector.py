from SessionInjector.browser.injector import to_playwright_cookies
from SessionInjector.cookies.models import Cookie

FUTURE = 4_102_444_800.0


def test_host_prefix_uses_url_and_no_domain():
    c = Cookie("__Host-session", "v", "example.com", "/", FUTURE,
               secure=False, http_only=True)
    (payload,) = to_playwright_cookies([c])
    # __Host- must be host-only: url instead of domain, forced Secure.
    assert payload.get("url") == "https://example.com/"
    assert "domain" not in payload
    assert payload["secure"] is True
    assert payload["path"] == "/"


def test_secure_prefix_forces_secure():
    c = Cookie("__Secure-3PSID", "v", ".google.com", "/", FUTURE, secure=False)
    (payload,) = to_playwright_cookies([c])
    assert payload["secure"] is True
    assert payload["domain"] == ".google.com"


def test_regular_cookie_uses_domain():
    c = Cookie("SID", "v", ".google.com", "/", FUTURE, secure=True)
    (payload,) = to_playwright_cookies([c])
    assert payload["domain"] == ".google.com"
    assert "url" not in payload
    assert payload["expires"] == FUTURE


def test_empty_domain_skipped():
    c = Cookie("x", "v", "", "/", FUTURE)
    assert to_playwright_cookies([c]) == []
