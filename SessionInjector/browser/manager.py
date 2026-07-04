"""Browser Manager.

Owns the Playwright + Chromium lifecycle. Playwright is imported lazily so the
rest of the application (parsing, analysis, health scoring) works with zero
browser dependencies installed — only the browser-based validation levels
require it.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional


class BrowserUnavailable(RuntimeError):
    """Raised when Playwright / Chromium is not installed or fails to start."""


def playwright_available() -> bool:
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


class BrowserManager:
    """Thin wrapper around a Playwright Chromium instance.

    Usage::

        with BrowserManager(headless=True) as mgr:
            context = mgr.new_context(cookies)
            page = context.new_page()
            page.goto(url)
    """

    def __init__(self, headless: bool = True, slow_mo: int = 0):
        self.headless = headless
        self.slow_mo = slow_mo
        self._pw = None
        self._browser = None

    # ------------------------------------------------------------------ #
    def start(self) -> "BrowserManager":
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:  # pragma: no cover - env dependent
            raise BrowserUnavailable(
                "Playwright is not installed. Run: pip install playwright "
                "&& playwright install chromium"
            ) from exc

        try:
            self._pw = sync_playwright().start()
            self._browser = self._pw.chromium.launch(
                headless=self.headless, slow_mo=self.slow_mo
            )
        except Exception as exc:  # pragma: no cover - env dependent
            self.stop()
            raise BrowserUnavailable(f"Failed to launch Chromium: {exc}") from exc
        return self

    def stop(self) -> None:
        if self._browser is not None:
            try:
                self._browser.close()
            except Exception:  # pragma: no cover - best effort
                pass
            self._browser = None
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:  # pragma: no cover
                pass
            self._pw = None

    # ------------------------------------------------------------------ #
    def new_context(self, cookies: Optional[list] = None):
        """Create a fresh, isolated context and (optionally) inject cookies.

        A new context is the clean way to swap sessions: the old context (with
        its old cookies) is discarded rather than mutated.
        """
        if self._browser is None:
            raise BrowserUnavailable("BrowserManager not started")
        context = self._browser.new_context()
        if cookies:
            from .injector import inject_cookies
            inject_cookies(context, cookies)
        return context

    # ------------------------------------------------------------------ #
    def __enter__(self) -> "BrowserManager":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()


@contextmanager
def browser_session(headless: bool = True) -> Iterator[BrowserManager]:
    mgr = BrowserManager(headless=headless)
    try:
        yield mgr.start()
    finally:
        mgr.stop()
