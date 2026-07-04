"""Cookie Analyzer.

Performs a full local inspection of a batch of cookies: expiry, attributes,
sizes, duplicates, broken characters/encoding and structural validity. Produces
an :class:`AnalysisReport`. No network access happens here.
"""
from __future__ import annotations

import re
import time

from .models import AnalysisReport, Cookie, Issue, Severity

# RFC 6265 token: cookie names can't contain control chars or separators.
_INVALID_NAME_RE = re.compile(r'[\x00-\x20()<>@,;:\\"/\[\]?={}\x7f]')
# Cookie values shouldn't contain control chars, spaces or these separators.
_INVALID_VALUE_RE = re.compile(r'[\x00-\x1f;\x7f]')

# Practical per-cookie size ceiling browsers enforce (~4 KB).
MAX_COOKIE_SIZE = 4096


def _has_broken_encoding(text: str) -> bool:
    """Detect the U+FFFD replacement char left by a bad decode."""
    return "�" in text


def analyze(cookies: list[Cookie], now: float | None = None) -> AnalysisReport:
    now = now if now is not None else time.time()
    report = AnalysisReport(total=len(cookies))
    seen: dict[tuple[str, str, str], int] = {}

    for cookie in cookies:
        cookie_valid = True

        # --- domain ---------------------------------------------------- #
        if not cookie.domain or "." not in cookie.registrable_domain:
            report.issues.append(
                Issue("bad_domain", f"Invalid domain: {cookie.domain!r}",
                      Severity.ERROR, cookie))
            cookie_valid = False
        else:
            report.domains.add(cookie.registrable_domain)

        # --- name ------------------------------------------------------ #
        if not cookie.name:
            report.issues.append(
                Issue("empty_name", "Cookie has no name", Severity.ERROR, cookie))
            cookie_valid = False
        elif _INVALID_NAME_RE.search(cookie.name):
            report.issues.append(
                Issue("bad_name", f"Illegal characters in name: {cookie.name!r}",
                      Severity.ERROR, cookie))
            cookie_valid = False

        # --- value / encoding ------------------------------------------ #
        if _INVALID_VALUE_RE.search(cookie.value):
            report.issues.append(
                Issue("bad_value", f"Illegal characters in value of {cookie.name!r}",
                      Severity.ERROR, cookie))
            cookie_valid = False
        if _has_broken_encoding(cookie.name) or _has_broken_encoding(cookie.value):
            report.issues.append(
                Issue("broken_encoding",
                      f"Broken encoding (replacement char) in {cookie.name!r}",
                      Severity.ERROR, cookie))
            cookie_valid = False

        # --- path ------------------------------------------------------ #
        if not cookie.path.startswith("/"):
            report.issues.append(
                Issue("bad_path", f"Path should start with '/': {cookie.path!r}",
                      Severity.WARNING, cookie))

        # --- size ------------------------------------------------------ #
        if cookie.size > MAX_COOKIE_SIZE:
            report.issues.append(
                Issue("oversize",
                      f"{cookie.name!r} is {cookie.size} bytes (> {MAX_COOKIE_SIZE})",
                      Severity.WARNING, cookie))

        # --- secure / httponly hints ----------------------------------- #
        if cookie.name.startswith("__Secure-") and not cookie.secure:
            report.issues.append(
                Issue("secure_prefix",
                      f"{cookie.name!r} uses __Secure- prefix but Secure is false",
                      Severity.WARNING, cookie))
        if cookie.name.startswith("__Host-") and (
            not cookie.secure or cookie.path != "/" or cookie.domain.startswith(".")
        ):
            report.issues.append(
                Issue("host_prefix",
                      f"{cookie.name!r} uses __Host- prefix but violates its rules",
                      Severity.WARNING, cookie))

        # --- expiry ---------------------------------------------------- #
        if cookie.is_expired(now):
            report.expired += 1
            report.issues.append(
                Issue("expired", f"{cookie.name!r} expired", Severity.WARNING, cookie))
            cookie_valid = False

        # --- duplicates ------------------------------------------------ #
        key = cookie.key()
        seen[key] = seen.get(key, 0) + 1
        if seen[key] == 2:  # count each duplicated key once
            report.duplicates += 1
            report.issues.append(
                Issue("duplicate",
                      f"Duplicate cookie {cookie.name!r} for {cookie.domain}{cookie.path}",
                      Severity.WARNING, cookie))

        # --- tally ----------------------------------------------------- #
        if cookie_valid:
            report.valid += 1
        else:
            report.invalid += 1

    return report
