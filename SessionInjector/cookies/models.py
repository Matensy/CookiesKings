"""Core data models for Session Injector.

These dataclasses are the single source of truth that flows through the whole
pipeline: Parser -> Analyzer -> Validator -> Browser.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class SameSite(str, Enum):
    """SameSite attribute values (Playwright-compatible casing)."""

    STRICT = "Strict"
    LAX = "Lax"
    NONE = "None"


@dataclass
class Cookie:
    """A single browser cookie.

    Mirrors the shape Playwright's ``context.add_cookies()`` expects, so a
    Cookie can be serialised straight into an injectable dict.
    """

    name: str
    value: str
    domain: str
    path: str = "/"
    expires: Optional[float] = None  # unix seconds; None == session cookie
    secure: bool = False
    http_only: bool = False
    same_site: Optional[SameSite] = None

    # ------------------------------------------------------------------ #
    # Derived helpers
    # ------------------------------------------------------------------ #
    @property
    def is_session_cookie(self) -> bool:
        """A cookie with no expiry lives only for the browser session."""
        return self.expires is None or self.expires <= 0

    def is_expired(self, now: Optional[float] = None) -> bool:
        """True when the cookie's expiry is in the past.

        Session cookies are treated as *not* expired (they simply have no
        persistent expiry to compare against).
        """
        if self.is_session_cookie:
            return False
        return float(self.expires) < (now if now is not None else time.time())

    @property
    def registrable_domain(self) -> str:
        """Domain without a leading dot, e.g. ``.google.com`` -> ``google.com``."""
        return self.domain[1:] if self.domain.startswith(".") else self.domain

    @property
    def size(self) -> int:
        """Approximate on-the-wire size (name + value in bytes)."""
        return len(self.name.encode("utf-8")) + len(self.value.encode("utf-8"))

    def to_playwright(self) -> dict:
        """Serialise to the dict shape Playwright's add_cookies expects."""
        data: dict = {
            "name": self.name,
            "value": self.value,
            "domain": self.domain,
            "path": self.path or "/",
            "secure": self.secure,
            "httpOnly": self.http_only,
        }
        if not self.is_session_cookie:
            data["expires"] = float(self.expires)
        if self.same_site is not None:
            data["sameSite"] = self.same_site.value
        return data

    def key(self) -> tuple[str, str, str]:
        """Identity used for duplicate detection: (name, domain, path)."""
        return (self.name, self.domain, self.path or "/")


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class Issue:
    """A single problem found while analysing a cookie."""

    code: str
    message: str
    severity: Severity = Severity.WARNING
    cookie: Optional[Cookie] = None


@dataclass
class AnalysisReport:
    """Aggregate result of analysing a batch of cookies."""

    total: int = 0
    valid: int = 0
    expired: int = 0
    invalid: int = 0
    duplicates: int = 0
    domains: set[str] = field(default_factory=set)
    issues: list[Issue] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"{self.total} cookies | {self.valid} valid | "
            f"{self.expired} expired | {self.invalid} invalid | "
            f"{self.duplicates} duplicates | {len(self.domains)} domains"
        )


class ValidationLevel(int, Enum):
    LOCAL = 1        # expiry / structural checks
    DOMAIN = 2       # domain matches the target service
    REQUIRED = 3     # required session cookies present
    BROWSER = 4      # real browser round-trip


class SessionStatus(str, Enum):
    FUNCTIONAL = "functional"       # login restored
    INVALID = "invalid"             # redirected to login
    EXPIRED = "expired"             # session expired
    INCOMPLETE = "incomplete"       # missing required cookies
    UNKNOWN = "unknown"             # could not determine


@dataclass
class ValidationResult:
    """Outcome of validating a set of cookies against a service."""

    service: str
    status: SessionStatus = SessionStatus.UNKNOWN
    reached_level: ValidationLevel = ValidationLevel.LOCAL
    final_url: Optional[str] = None
    logged_in: Optional[bool] = None
    missing_required: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.status is SessionStatus.FUNCTIONAL
