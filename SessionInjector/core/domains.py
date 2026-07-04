"""Domain grouping helpers.

Cookies carry raw domains like ``.google.com`` or ``accounts.google.com``. For
the UI we want to group them by the real *site* (eTLD+1) so a user sees
``google.com`` once instead of five Google subdomains, and can open a browser
logged into everything for that site at once.

The eTLD list here is a small practical subset — enough for the common
multi-label TLDs — not a full Public Suffix List.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from ..cookies.models import Cookie

# Common two-level public suffixes (so example.co.uk -> example.co.uk).
_TWO_LEVEL_SUFFIXES = {
    "co.uk", "org.uk", "gov.uk", "ac.uk", "co.jp", "co.kr", "co.in",
    "com.br", "com.au", "com.mx", "com.ar", "com.tr", "com.cn", "com.hk",
    "com.sg", "com.tw", "net.br", "org.br", "gov.br", "co.za", "co.nz",
}


def site_of(domain: str) -> str:
    """Return the registrable site (eTLD+1) for a cookie domain."""
    d = domain.lstrip(".").lower()
    parts = d.split(".")
    if len(parts) <= 2:
        return d
    last_two = ".".join(parts[-2:])
    if last_two in _TWO_LEVEL_SUFFIXES and len(parts) >= 3:
        return ".".join(parts[-3:])
    return last_two


@dataclass
class DomainGroup:
    site: str
    cookies: list[Cookie] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.cookies)

    def valid(self, now: float | None = None) -> int:
        now = now if now is not None else time.time()
        return sum(1 for c in self.cookies if not c.is_expired(now))


def group_by_site(cookies: list[Cookie]) -> list[DomainGroup]:
    """Group cookies by registrable site, sorted by valid-cookie count desc."""
    groups: dict[str, DomainGroup] = {}
    for c in cookies:
        site = site_of(c.domain)
        groups.setdefault(site, DomainGroup(site)).cookies.append(c)
    return sorted(groups.values(), key=lambda g: (-g.valid(), g.site))


def cookies_for_site(cookies: list[Cookie], site: str) -> list[Cookie]:
    """All cookies that belong to ``site`` (including its subdomains)."""
    return [c for c in cookies if site_of(c.domain) == site]
