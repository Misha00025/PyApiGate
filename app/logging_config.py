"""
Logging configuration for PyApiGate.
Sets up console and optional file logging from app config.
"""

from __future__ import annotations

import logging
import sys
from typing import Any


def setup_logging(config: dict[str, Any]) -> None:
    """
    Configures root logger based on app config.

    Args:
        config: Merged app configuration dict from load_app_config().
    """
    logging_cfg = config.get("logging", {})
    level = getattr(logging, logging_cfg.get("level", "INFO").upper(), logging.INFO)
    log_format = logging_cfg.get(
        "format",
        "%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    )

    # Root logger
    root = logging.getLogger()
    root.setLevel(level)

    # Remove default handlers to avoid duplicates
    for handler in root.handlers[:]:
        root.removeHandler(handler)

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(logging.Formatter(log_format))
    root.addHandler(console)

    # File handler (optional)
    log_file = logging_cfg.get("file")
    if log_file:
        try:
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(level)
            file_handler.setFormatter(logging.Formatter(log_format))
            root.addHandler(file_handler)
        except (IOError, OSError) as e:
            root.warning("Failed to open log file '%s': %s. Logging to console only.", log_file, e)

    # Suppress noisy library loggers
    for lib in ("uvicorn", "uvicorn.access", "httpx", "httpcore"):
        lib_logger = logging.getLogger(lib)
        lib_logger.setLevel(logging.WARNING)
        lib_logger.propagate = False
