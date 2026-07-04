from SessionInjector.browser.validator import validate_local
from SessionInjector.config.profiles import GOOGLE
from SessionInjector.cookies.models import Cookie, SameSite, SessionStatus
from SessionInjector.core.health import compute_health

NOW = 1_700_000_000.0


def google_cookie(name, **kw):
    kw.setdefault("expires", NOW + 100_000)
    return Cookie(name=name, value="v", domain=".google.com", **kw)


def full_google_set():
    return [google_cookie(n, secure=True, http_only=True, same_site=SameSite.NONE)
            for n in GOOGLE.required_cookies]


def test_local_no_cookies_is_invalid():
    r = validate_local([], GOOGLE, now=NOW)
    assert r.status is SessionStatus.INVALID


def test_local_all_expired_is_expired():
    cookies = [google_cookie(n, expires=NOW - 1) for n in GOOGLE.required_cookies]
    r = validate_local(cookies, GOOGLE, now=NOW)
    assert r.status is SessionStatus.EXPIRED


def test_local_missing_half_is_incomplete():
    cookies = [google_cookie("SID")]  # only 1 of 6 required
    r = validate_local(cookies, GOOGLE, now=NOW)
    assert r.status is SessionStatus.INCOMPLETE
    assert "SAPISID" in r.missing_required


def test_local_full_set_is_unknown_pending_browser():
    r = validate_local(full_google_set(), GOOGLE, now=NOW)
    assert r.status is SessionStatus.UNKNOWN


def test_health_full_set_scores_high_locally():
    hs = compute_health(full_google_set(), GOOGLE, validation=None, now=NOW)
    assert hs.score >= 80
    assert "browser" not in hs.factors  # weight redistributed when no test


def test_health_empty_scores_zero():
    hs = compute_health([], GOOGLE, validation=None, now=NOW)
    assert hs.score == 0
    assert hs.verified is False
    assert "não verificado" in hs.grade


def test_health_stars_scale():
    hs = compute_health(full_google_set(), GOOGLE, validation=None, now=NOW)
    assert len(hs.stars) == 5
