"""Tests for the positive-evidence login evaluation and honest health grade."""
from SessionInjector.browser.validator import evaluate_login
from SessionInjector.config.profiles import GITHUB, GOOGLE
from SessionInjector.cookies.models import Cookie, SameSite, SessionStatus, ValidationResult
from SessionInjector.core.health import compute_health

FUTURE = 4_102_444_800.0


def test_bounced_to_signin_is_invalid():
    status, logged_in, _ = evaluate_login(
        "https://accounts.google.com/v3/signin/identifier", GOOGLE)
    assert status is SessionStatus.INVALID
    assert logged_in is False


def test_stayed_on_protected_host_is_functional():
    status, logged_in, _ = evaluate_login(
        "https://myaccount.google.com/", GOOGLE)
    assert status is SessionStatus.FUNCTIONAL
    assert logged_in is True


def test_dom_marker_absent_is_invalid():
    status, logged_in, _ = evaluate_login(
        "https://github.com/settings/profile", GITHUB, dom_logged_in=False)
    assert status is SessionStatus.INVALID


def test_unknown_when_no_evidence():
    # A host we don't recognise as a logged-in host, and no sign-in marker.
    status, logged_in, _ = evaluate_login("https://example.com/", GOOGLE)
    assert status is SessionStatus.UNKNOWN
    assert logged_in is None


def test_no_optimistic_functional():
    """The old bug: an unrelated final URL must NOT be reported as functional."""
    status, _, _ = evaluate_login("https://some-consent-page.google.com/", GOOGLE)
    assert status is not SessionStatus.FUNCTIONAL


def _full_google():
    return [Cookie(n, "v", ".google.com", "/", FUTURE, True, True, SameSite.NONE)
            for n in GOOGLE.required_cookies]


def test_local_grade_never_claims_logged_in():
    hs = compute_health(_full_google(), GOOGLE, validation=None)
    assert hs.verified is False
    assert "Logado" not in hs.grade  # must not promise a working session


def test_verified_grade_reflects_browser_result():
    v = ValidationResult(service="google", status=SessionStatus.FUNCTIONAL,
                         logged_in=True)
    hs = compute_health(_full_google(), GOOGLE, validation=v)
    assert hs.verified is True
    assert hs.logged_in is True
    assert "Logado" in hs.grade

    v2 = ValidationResult(service="google", status=SessionStatus.INVALID,
                          logged_in=False)
    hs2 = compute_health(_full_google(), GOOGLE, validation=v2)
    assert hs2.verified is True
    assert "Deslogado" in hs2.grade
