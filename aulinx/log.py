"""Structured logging for Aulinx — file + console output."""

import logging
from pathlib import Path

LOG_DIR = Path.home() / ".local/share/aulinx"
LOG_FILE = LOG_DIR / "aulinx.log"


def setup_logging(verbose: bool = False):
    """Configure logging for the application.

    Console: warnings and errors only (unless verbose).
    File: everything (debug+) to ~/.local/share/aulinx/aulinx.log.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # Root logger
    root = logging.getLogger("aulinx")
    root.setLevel(logging.DEBUG)

    # File handler — everything
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    root.addHandler(file_handler)

    # Console handler — warnings only (unless verbose)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if verbose else logging.WARNING)
    console_handler.setFormatter(logging.Formatter(
        "[%(levelname)s] %(message)s",
    ))
    root.addHandler(console_handler)

    return root


def get_logger(name: str) -> logging.Logger:
    """Get a named logger under the aulinx namespace."""
    return logging.getLogger(f"aulinx.{name}")
