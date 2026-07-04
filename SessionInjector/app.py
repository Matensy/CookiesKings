"""Session Injector — CLI entry point.

Ties the whole pipeline together:

    import -> analyze -> validate -> (inject + browser test) -> score

Examples
--------
    # Analyse a cookie export and print the report:
    python -m SessionInjector.app analyze cookies.json

    # Full run: import, analyse, and test the session in a real browser:
    python -m SessionInjector.app test cookies.txt

    # Local-only (no browser), restricted to a service:
    python -m SessionInjector.app test cookies.json --no-browser --service google

    # Import cookies, open a visible browser and inject them:
    python -m SessionInjector.app open cookies.json --service google

For authorised use with your own accounts / sessions only.
"""
from __future__ import annotations

import argparse
import sys

from .config.profiles import PROFILES
from .cookies.analyzer import analyze
from .cookies.loader import load_files
from .cookies.parser import ParseError
from .core.logging_config import setup_logging
from .core.session_tester import test_sessions
from .ui.dashboard import render_analysis, render_session


def _load(paths: list[str], logger):
    cookies = load_files(paths)
    errors = getattr(cookies, "errors", [])
    for path, msg in errors:
        logger.warning("Could not import %s: %s", path, msg)
    logger.info("Imported %d cookies from %d file(s).", len(cookies), len(paths))
    if not cookies:
        logger.error("No cookies imported — nothing to do.")
    return cookies


def cmd_analyze(args, logger) -> int:
    cookies = _load(args.files, logger)
    if not cookies:
        return 1
    report = analyze(cookies)
    logger.info(report.summary())
    print(render_analysis(report))
    return 0


def cmd_test(args, logger) -> int:
    cookies = _load(args.files, logger)
    if not cookies:
        return 1

    report = analyze(cookies)
    print(render_analysis(report))
    print()

    session = test_sessions(
        cookies,
        services=[args.service] if args.service else None,
        use_browser=not args.no_browser,
        headless=not args.headed,
    )
    print(render_session(session))
    best = session.best()
    return 0 if best and best.health.score >= 60 else 2


def cmd_open(args, logger) -> int:
    """Import cookies, inject them, and leave a visible browser open."""
    from .browser.manager import BrowserManager, BrowserUnavailable, playwright_available

    cookies = _load(args.files, logger)
    if not cookies:
        return 1
    if not playwright_available():
        logger.error("Playwright is required for 'open'. "
                     "pip install playwright && playwright install chromium")
        return 1

    profile = PROFILES.get(args.service)
    scoped = (
        [c for c in cookies if profile.owns(c.registrable_domain)]
        if profile else cookies
    )
    url = profile.test_url if profile else "about:blank"

    try:
        with BrowserManager(headless=False) as mgr:
            context = mgr.new_context(scoped)
            page = context.new_page()
            logger.info("Injected %d cookies; navigating to %s", len(scoped), url)
            page.goto(url, wait_until="domcontentloaded")
            logger.info("Final URL: %s", page.url)
            input("Browser open — press Enter to close…")
    except BrowserUnavailable as exc:
        logger.error("%s", exc)
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="session-injector",
        description="Import, analyse, validate and inject browser cookie sessions "
                    "(authorised use with your own accounts only).",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")
    sub = parser.add_subparsers(dest="command", required=True)

    p_analyze = sub.add_parser("analyze", help="Import and analyse cookies")
    p_analyze.add_argument("files", nargs="+", help="Cookie file(s) to import")

    p_test = sub.add_parser("test", help="Analyse + validate + score sessions")
    p_test.add_argument("files", nargs="+", help="Cookie file(s) to import")
    p_test.add_argument("--service", choices=sorted(PROFILES), help="Restrict to one service")
    p_test.add_argument("--no-browser", action="store_true", help="Skip the browser test")
    p_test.add_argument("--headed", action="store_true", help="Show the browser window")

    p_open = sub.add_parser("open", help="Inject cookies into a visible browser")
    p_open.add_argument("files", nargs="+", help="Cookie file(s) to import")
    p_open.add_argument("--service", choices=sorted(PROFILES), help="Target service")

    return parser


def main(argv: list[str] | None = None) -> int:
    import logging

    parser = build_parser()
    args = parser.parse_args(argv)
    logger = setup_logging(logging.DEBUG if args.verbose else logging.INFO)

    handlers = {"analyze": cmd_analyze, "test": cmd_test, "open": cmd_open}
    try:
        return handlers[args.command](args, logger)
    except ParseError as exc:
        logger.error("Parse error: %s", exc)
        return 1
    except KeyboardInterrupt:
        logger.info("Interrupted.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
