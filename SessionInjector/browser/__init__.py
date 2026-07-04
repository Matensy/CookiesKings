"""Browser automation layer: manager, injector, validator."""
from .injector import inject_cookies, to_playwright_cookies
from .manager import (
    BrowserManager,
    BrowserUnavailable,
    browser_session,
    open_session,
    playwright_available,
)
from .validator import validate, validate_browser, validate_local

__all__ = [
    "inject_cookies",
    "to_playwright_cookies",
    "BrowserManager",
    "BrowserUnavailable",
    "browser_session",
    "open_session",
    "playwright_available",
    "validate",
    "validate_browser",
    "validate_local",
]
