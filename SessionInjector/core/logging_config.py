"""Centralised logging setup.

Writes both to the console and to ``logs/session_injector.log`` so every import,
analysis and injection leaves a trail — useful for a portfolio project that
wants to demonstrate observability.
"""
from __future__ import annotations

import logging
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_FILE = LOG_DIR / "session_injector.log"

_FORMAT = "[%(levelname)s] %(asctime)s %(name)s: %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_logging(level: int = logging.INFO, to_file: bool = True) -> logging.Logger:
    logger = logging.getLogger("session_injector")
    if logger.handlers:  # already configured
        logger.setLevel(level)
        return logger

    logger.setLevel(level)
    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    if to_file:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    logger.propagate = False
    return logger


def get_logger(name: str = "session_injector") -> logging.Logger:
    return logging.getLogger(name)
