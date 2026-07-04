import time

from SessionInjector.cookies.analyzer import analyze
from SessionInjector.cookies.models import Cookie

NOW = 1_700_000_000.0


def mk(name="SID", value="x", domain=".google.com", **kw):
    return Cookie(name=name, value=value, domain=domain, **kw)


def test_counts_valid_expired_invalid():
    cookies = [
        mk(expires=NOW + 1000),               # valid
        mk(name="OLD", expires=NOW - 1000),   # expired
        mk(name="bad name", value="v"),       # invalid name
    ]
    report = analyze(cookies, now=NOW)
    assert report.total == 3
    assert report.expired == 1
    assert report.invalid == 2  # expired one + bad-name one
    assert report.valid == 1


def test_duplicate_detection():
    c = mk(expires=NOW + 1000)
    report = analyze([c, mk(expires=NOW + 1000)], now=NOW)
    assert report.duplicates == 1


def test_broken_encoding_flagged():
    report = analyze([mk(value="br�ken", expires=NOW + 1000)], now=NOW)
    codes = {i.code for i in report.issues}
    assert "broken_encoding" in codes
    assert report.invalid == 1


def test_domains_collected():
    report = analyze([mk(domain=".google.com", expires=NOW + 1),
                      mk(domain=".github.com", expires=NOW + 1)], now=NOW)
    assert report.domains == {"google.com", "github.com"}


def test_oversize_warning():
    big = mk(value="a" * 5000, expires=NOW + 1000)
    report = analyze([big], now=NOW)
    assert any(i.code == "oversize" for i in report.issues)
