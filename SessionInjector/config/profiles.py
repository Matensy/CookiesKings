"""Service profiles.

Each profile describes what a "healthy" authenticated session looks like for a
given service: which domain owns it, which cookies are essential, and how to
tell (by URL and/or DOM) whether the session was restored in a real browser.

These are used by the Validator (levels 2-4), the Session Tester, and the
Health Score. Add new services here without touching the engine.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ServiceProfile:
    key: str
    label: str
    # A cookie belongs to this service if its registrable domain matches any.
    domains: tuple[str, ...]
    # Cookies that must be present for the session to have a chance of working.
    required_cookies: tuple[str, ...] = ()
    # The URL we navigate to when browser-testing.
    test_url: str = ""
    # Substrings that, if present in the FINAL url, mean "not logged in".
    signed_out_url_markers: tuple[str, ...] = ()
    # A DOM selector whose presence indicates a logged-in state (optional).
    logged_in_selector: str = ""

    def owns(self, registrable_domain: str) -> bool:
        rd = registrable_domain.lower()
        return any(rd == d or rd.endswith("." + d) for d in self.domains)


GOOGLE = ServiceProfile(
    key="google",
    label="Google",
    domains=("google.com",),
    required_cookies=("SID", "HSID", "SSID", "SAPISID", "APISID", "LSID"),
    test_url="https://accounts.google.com",
    signed_out_url_markers=("signin", "ServiceLogin", "/accounts/Login"),
    logged_in_selector="a[aria-label*='Google Account'], img[alt*='Account']",
)

YOUTUBE = ServiceProfile(
    key="youtube",
    label="YouTube",
    domains=("youtube.com",),
    required_cookies=("SID", "SAPISID", "APISID", "HSID", "SSID"),
    test_url="https://www.youtube.com/account",
    signed_out_url_markers=("accounts.google.com/ServiceLogin", "signin"),
    logged_in_selector="#avatar-btn, ytd-topbar-menu-button-renderer",
)

GITHUB = ServiceProfile(
    key="github",
    label="GitHub",
    domains=("github.com",),
    required_cookies=("user_session", "__Host-user_session_same_site"),
    test_url="https://github.com/settings/profile",
    signed_out_url_markers=("/login", "/session"),
    logged_in_selector="summary[aria-label='View profile and more']",
)


PROFILES: dict[str, ServiceProfile] = {
    p.key: p for p in (GOOGLE, YOUTUBE, GITHUB)
}


def profile_for_domain(registrable_domain: str) -> ServiceProfile | None:
    for profile in PROFILES.values():
        if profile.owns(registrable_domain):
            return profile
    return None


def get_profile(key: str) -> ServiceProfile | None:
    return PROFILES.get(key.lower())
