from SessionInjector.core.domains import cookies_for_site, group_by_site, site_of
from SessionInjector.cookies.models import Cookie

FUTURE = 4_102_444_800.0  # year 2100 — valid regardless of the real clock
PAST = 1_000.0            # long expired


def mk(domain, name="c", expires=FUTURE):
    return Cookie(name=name, value="v", domain=domain, expires=expires)


def test_site_of_basic():
    assert site_of(".google.com") == "google.com"
    assert site_of("accounts.google.com") == "google.com"
    assert site_of("mail.google.com") == "google.com"


def test_site_of_two_level_suffix():
    assert site_of("www.example.co.uk") == "example.co.uk"
    assert site_of(".loja.com.br") == "loja.com.br"


def test_group_by_site_merges_subdomains():
    cookies = [mk(".google.com"), mk("accounts.google.com"), mk(".github.com")]
    groups = {g.site: g for g in group_by_site(cookies)}
    assert set(groups) == {"google.com", "github.com"}
    assert groups["google.com"].total == 2


def test_group_valid_count_and_sort():
    cookies = [
        mk(".a.com"),
        mk(".a.com", name="d", expires=PAST),   # expired
        mk(".b.com"),
        mk(".b.com", name="e"),
    ]
    groups = group_by_site(cookies)
    # b.com has 2 valid, a.com has 1 valid -> b first
    assert groups[0].site == "b.com"
    assert groups[0].valid() == 2
    a = next(g for g in groups if g.site == "a.com")
    assert a.valid() == 1
    assert a.total == 2


def test_cookies_for_site():
    cookies = [mk(".google.com"), mk("mail.google.com"), mk(".other.com")]
    scoped = cookies_for_site(cookies, "google.com")
    assert len(scoped) == 2
