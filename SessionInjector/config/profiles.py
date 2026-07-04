"""Service profiles.

Each profile describes what a "healthy" authenticated session looks like for a
given service: which domain owns it, which cookies are essential, and how to
tell — from the final URL and/or the DOM — whether the session was actually
restored in a real browser.

Login detection uses *positive evidence*: after navigating to a protected page,
we only call it logged-in if we either (a) stayed on the expected host without
being bounced to a sign-in page, or (b) found a logged-in DOM marker. Anything
else is reported as INVALID or UNKNOWN — never an optimistic "functional".
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ServiceProfile:
    key: str
    label: str
    # A cookie belongs to this service if its registrable domain matches any.
    domains: tuple[str, ...]
    # Cookies that must be present for the session to have a chance of working.
    required_cookies: tuple[str, ...] = ()
    # The (protected) URL we navigate to when browser-testing.
    test_url: str = ""
    # Substrings that, if present in the FINAL url, mean "not logged in".
    signed_out_url_markers: tuple[str, ...] = ()
    # Hosts we expect to *stay* on when logged in (positive URL evidence).
    logged_in_hosts: tuple[str, ...] = ()
    # A DOM selector whose presence confirms a logged-in state (optional).
    logged_in_selector: str = ""

    def owns(self, registrable_domain: str) -> bool:
        rd = registrable_domain.lower()
        return any(rd == d or rd.endswith("." + d) for d in self.domains)


GOOGLE = ServiceProfile(
    key="google",
    label="Google",
    domains=("google.com",),
    # The modern Google session leans on the __Secure-*PSID / *PAPISID family
    # in addition to the classic set; without them the session rarely restores.
    required_cookies=(
        "SID", "HSID", "SSID", "SAPISID", "APISID",
        "__Secure-1PSID", "__Secure-3PSID",
        "__Secure-1PAPISID", "__Secure-3PAPISID",
    ),
    test_url="https://myaccount.google.com/",
    signed_out_url_markers=(
        "signin", "ServiceLogin", "/v3/signin", "accounts.google.com/Login",
    ),
    logged_in_hosts=("myaccount.google.com",),
    logged_in_selector="",
)

YOUTUBE = ServiceProfile(
    key="youtube",
    label="YouTube",
    domains=("youtube.com",),
    required_cookies=(
        "SID", "HSID", "SSID", "SAPISID", "APISID",
        "__Secure-1PSID", "__Secure-3PSID",
    ),
    test_url="https://www.youtube.com/account",
    signed_out_url_markers=("accounts.google.com", "ServiceLogin", "signin"),
    logged_in_hosts=("youtube.com", "www.youtube.com"),
    logged_in_selector="#avatar-btn, ytd-topbar-menu-button-renderer",
)

X = ServiceProfile(
    key="x",
    label="X / Twitter",
    domains=("x.com", "twitter.com"),
    required_cookies=("auth_token", "ct0"),
    test_url="https://x.com/home",
    signed_out_url_markers=("/login", "/i/flow/login", "/?logout", "/flow/"),
    logged_in_hosts=("x.com", "twitter.com"),
    logged_in_selector="a[data-testid='AppTabBar_Profile_Link']",
)

INSTAGRAM = ServiceProfile(
    key="instagram",
    label="Instagram",
    domains=("instagram.com",),
    required_cookies=("sessionid", "ds_user_id"),
    test_url="https://www.instagram.com/accounts/edit/",
    signed_out_url_markers=("/accounts/login", "/login"),
    logged_in_hosts=("instagram.com", "www.instagram.com"),
    logged_in_selector="",
)

GITHUB = ServiceProfile(
    key="github",
    label="GitHub",
    domains=("github.com",),
    required_cookies=("user_session",),
    test_url="https://github.com/settings/profile",
    signed_out_url_markers=("/login", "/session"),
    logged_in_hosts=("github.com",),
    logged_in_selector="summary[aria-label='View profile and more']",
)

REDDIT = ServiceProfile(
    key="reddit",
    label="Reddit",
    domains=("reddit.com",),
    required_cookies=("reddit_session", "token_v2"),
    test_url="https://www.reddit.com/settings/",
    signed_out_url_markers=("/login", "/account/login"),
    logged_in_hosts=("reddit.com", "www.reddit.com"),
    logged_in_selector="",
)


PROFILES: dict[str, ServiceProfile] = {
    p.key: p for p in (GOOGLE, YOUTUBE, X, INSTAGRAM, GITHUB, REDDIT)
}


def profile_for_domain(registrable_domain: str) -> ServiceProfile | None:
    for profile in PROFILES.values():
        if profile.owns(registrable_domain):
            return profile
    return None


def get_profile(key: str) -> ServiceProfile | None:
    return PROFILES.get(key.lower())
