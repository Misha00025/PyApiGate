"""
Logging configuration for PyApiGate.
Sets up console and optional file logging from app config.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from typing import Any

from app.logging_formatter import SourceExpressionFormatter


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
    console.setFormatter(SourceExpressionFormatter(log_format))
    root.addHandler(console)

    # File handler (optional)
    log_file = logging_cfg.get("file")
    if log_file:
        try:
            rotation = logging_cfg.get("rotation")
            if rotation and isinstance(rotation, dict):
                rot_type = rotation.get("type")
                backup_count = rotation.get("backup_count", 7)
                if rot_type == "size":
                    file_handler = RotatingFileHandler(
                        log_file,
                        maxBytes=rotation.get("max_bytes", 10 * 1024 * 1024),
                        backupCount=backup_count,
                    )
                elif rot_type == "timed":
                    file_handler = TimedRotatingFileHandler(
                        log_file,
                        when=rotation.get("when", "midnight"),
                        interval=rotation.get("interval", 1),
                        backupCount=backup_count,
                    )
                else:
                    file_handler = logging.FileHandler(log_file)
            else:
                file_handler = logging.FileHandler(log_file)

            file_handler.setLevel(level)
            file_handler.setFormatter(SourceExpressionFormatter(log_format))
            root.addHandler(file_handler)
        except (IOError, OSError, ValueError) as e:
            root.warning("Failed to set up log file '%s': %s. Logging to console only.", log_file, e)

    # Suppress noisy library loggers
    for lib in ("uvicorn", "uvicorn.access", "httpx", "httpcore"):
        lib_logger = logging.getLogger(lib)
        lib_logger.setLevel(logging.WARNING)
        lib_logger.propagate = False
