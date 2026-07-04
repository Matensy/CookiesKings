"""Cookie parsers.

Turns raw exported cookie data (Netscape ``cookies.txt`` or the JSON shapes
produced by common browser-extension exporters) into :class:`Cookie` objects.
"""
from __future__ import annotations

import json
from typing import Iterable

from .models import Cookie, SameSite


class ParseError(ValueError):
    """Raised when a payload cannot be parsed in the requested format."""


def _coerce_expires(raw) -> float | None:
    if raw in (None, "", 0, "0"):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def _coerce_same_site(raw) -> SameSite | None:
    if not raw:
        return None
    normalized = str(raw).strip().lower()
    mapping = {
        "strict": SameSite.STRICT,
        "lax": SameSite.LAX,
        "none": SameSite.NONE,
        "no_restriction": SameSite.NONE,
        "unspecified": None,
    }
    return mapping.get(normalized)


# --------------------------------------------------------------------------- #
# Netscape cookies.txt
# --------------------------------------------------------------------------- #
def parse_netscape(text: str) -> list[Cookie]:
    """Parse the classic Netscape ``cookies.txt`` format.

    Each data line has 7 tab-separated fields::

        domain  include_subdomains  path  secure  expires  name  value

    ``#HttpOnly_`` prefixes on the domain field are honoured.
    """
    cookies: list[Cookie] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        raw = line.rstrip("\n")
        if not raw.strip():
            continue
        # Comment lines, except the special #HttpOnly_ marker.
        if raw.startswith("#") and not raw.startswith("#HttpOnly_"):
            continue

        http_only = False
        if raw.startswith("#HttpOnly_"):
            http_only = True
            raw = raw[len("#HttpOnly_"):]

        fields = raw.split("\t")
        if len(fields) != 7:
            # Tolerate whitespace-separated exports as a fallback.
            fields = raw.split()
            if len(fields) != 7:
                raise ParseError(
                    f"Netscape line {lineno}: expected 7 fields, got {len(fields)}"
                )

        domain, _include_sub, path, secure, expires, name, value = fields
        cookies.append(
            Cookie(
                name=name,
                value=value,
                domain=domain,
                path=path or "/",
                expires=_coerce_expires(expires),
                secure=secure.strip().upper() == "TRUE",
                http_only=http_only,
            )
        )
    return cookies


# --------------------------------------------------------------------------- #
# JSON exports (EditThisCookie / Cookie-Editor / generic)
# --------------------------------------------------------------------------- #
def parse_json(text: str) -> list[Cookie]:
    """Parse the JSON export shapes used by common cookie extensions.

    Accepts either a top-level list of cookie objects, or an object with a
    ``cookies`` key holding that list. Field names are normalised across the
    EditThisCookie / Cookie-Editor / Playwright variants.
    """
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:  # pragma: no cover - trivial
        raise ParseError(f"Invalid JSON: {exc}") from exc

    if isinstance(data, dict) and "cookies" in data:
        data = data["cookies"]
    if not isinstance(data, list):
        raise ParseError("JSON cookie export must be a list of cookie objects")

    return list(_cookies_from_dicts(data))


def _cookies_from_dicts(items: Iterable[dict]) -> Iterable[Cookie]:
    for item in items:
        if not isinstance(item, dict):
            raise ParseError(f"Cookie entry is not an object: {item!r}")

        name = item.get("name")
        value = item.get("value", "")
        domain = item.get("domain") or item.get("Domain")
        if not name or not domain:
            # Skip incomplete records rather than aborting the whole import.
            continue

        expires = item.get("expirationDate", item.get("expires"))
        secure = bool(item.get("secure", False))
        http_only = bool(item.get("httpOnly", item.get("httponly", False)))

        yield Cookie(
            name=str(name),
            value=str(value),
            domain=str(domain),
            path=str(item.get("path", "/")) or "/",
            expires=_coerce_expires(expires),
            secure=secure,
            http_only=http_only,
            same_site=_coerce_same_site(item.get("sameSite", item.get("samesite"))),
        )
