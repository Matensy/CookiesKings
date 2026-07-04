"""Cookie importer / loader.

Detects the format of exported cookie data, loads one-or-many files, and
returns parsed :class:`Cookie` objects. This is the entry edge of the
pipeline (the "Cookie Importer" module).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .models import Cookie
from .parser import ParseError, parse_json, parse_netscape

CookieFormat = str  # "netscape" | "json"


class CookieBatch(list):
    """A list of cookies that also carries per-file import errors."""

    errors: list[tuple[str, str]]

    def __init__(self, *args):
        super().__init__(*args)
        self.errors = []


def detect_format(text: str) -> CookieFormat:
    """Best-effort format sniffing from raw text content."""
    stripped = text.lstrip()
    if not stripped:
        raise ParseError("Empty cookie payload")

    if stripped[0] in "[{":
        # Confirm it actually parses as JSON before committing.
        try:
            json.loads(stripped)
            return "json"
        except json.JSONDecodeError:
            pass

    # Netscape files usually carry this header, or start with a domain token.
    if "# Netscape HTTP Cookie File" in text or "\t" in text or "#HttpOnly_" in text:
        return "netscape"

    # Fall back: a domain-looking first token means Netscape.
    first = stripped.splitlines()[0].split()
    if first and ("." in first[0] or first[0].startswith("#HttpOnly_")):
        return "netscape"

    raise ParseError("Could not detect cookie format (not JSON or Netscape)")


def parse_text(text: str, fmt: CookieFormat | None = None) -> list[Cookie]:
    """Parse raw text, auto-detecting the format when not given."""
    fmt = fmt or detect_format(text)
    if fmt == "json":
        return parse_json(text)
    if fmt == "netscape":
        return parse_netscape(text)
    raise ParseError(f"Unsupported format: {fmt}")


def load_file(path: str | Path) -> list[Cookie]:
    """Load and parse a single cookie file."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(p)
    text = p.read_text(encoding="utf-8", errors="replace")
    fmt = "json" if p.suffix.lower() == ".json" else None
    return parse_text(text, fmt)


def load_files(paths: Iterable[str | Path]) -> list[Cookie]:
    """Load and concatenate cookies from multiple files.

    Files that fail to parse are skipped; their errors are attached to the
    returned list via the ``.errors`` attribute for the UI/log layer.
    """
    all_cookies = CookieBatch()
    for path in paths:
        try:
            all_cookies.extend(load_file(path))
        except (ParseError, OSError) as exc:
            all_cookies.errors.append((str(path), str(exc)))
    return all_cookies
