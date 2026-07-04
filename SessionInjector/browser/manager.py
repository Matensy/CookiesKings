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
    def is_connected(self) -> bool:
        """True while the Chromium process is alive (windows still open)."""
        try:
            return self._browser is not None and self._browser.is_connected()
        except Exception:  # pragma: no cover
            return False

    # ------------------------------------------------------------------ #
    def __enter__(self) -> "BrowserManager":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.stop()


def open_session(cookies: list, url: str, logger=None, profile=None) -> None:
    """Open a **visible** browser, inject cookies, navigate, and hold it open.

    When a ``profile`` is given, the real login state is checked after the page
    settles and reported honestly (✓ logado / ✗ deslogado / não confirmado) —
    so the user is never told a session works when it doesn't.

    Blocks until the user closes the browser window, so this must be run on its
    own thread (Playwright's sync API is single-threaded). Raises
    :class:`BrowserUnavailable` if Chromium can't start.
    """
    import time

    mgr = BrowserManager(headless=False).start()
    try:
        context = mgr.new_context(cookies)
        page = context.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            try:
                page.wait_for_load_state("networkidle", timeout=6_000)
            except Exception:
                pass
            final_url = page.url
            if logger:
                logger.info("Aberto %s (URL final: %s)", url, final_url)
            _report_login(page, final_url, profile, logger)
        except Exception as exc:  # navigation hiccups shouldn't kill the window
            if logger:
                logger.warning("Falha ao navegar para %s: %s", url, exc)
        # Hold the thread until the user closes the browser.
        while mgr.is_connected():
            time.sleep(0.5)
    finally:
        mgr.stop()
        if logger:
            logger.info("Navegador fechado (%s).", url)


def _report_login(page, final_url: str, profile, logger) -> None:
    """Log an honest verdict about whether the session actually restored."""
    if logger is None or profile is None:
        return
    # Imported here to avoid a circular import at module load.
    from .validator import evaluate_login
    from ..cookies.models import SessionStatus

    dom = None
    if profile.logged_in_selector:
        try:
            dom = page.query_selector(profile.logged_in_selector) is not None
        except Exception:
            dom = None

    status, _logged_in, note = evaluate_login(final_url, profile, dom)
    if status is SessionStatus.FUNCTIONAL:
        logger.info("✅ %s: sessão restaurada — VOCÊ ESTÁ LOGADO.", profile.label)
    elif status is SessionStatus.INVALID:
        logger.warning("❌ %s: sessão NÃO restaurada — pedindo login. %s",
                       profile.label, note)
    else:
        logger.warning("⚠️ %s: não deu para confirmar o login. %s",
                       profile.label, note)


@contextmanager
def browser_session(headless: bool = True) -> Iterator[BrowserManager]:
    mgr = BrowserManager(headless=headless)
    try:
        yield mgr.start()
    finally:
        mgr.stop()
