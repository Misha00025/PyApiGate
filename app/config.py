"""
Application configuration loading and validation.
Loads app.json from configs/, merges with defaults from configs_default/.
"""

from __future__ import annotations

import json
import os
import logging
import shutil
from typing import Any

logger = logging.getLogger(__name__)

DEFAULTS_DIR = "configs_default"
CONFIG_DIR = "configs"
CONFIG_FILE = "app.json"


def load_app_config(config_dir: str = CONFIG_DIR) -> dict[str, Any]:
    """
    Loads app configuration, merging user config over defaults.

    - Reads defaults from configs_default/app.json
    - If configs/app.json doesn't exist, creates it from defaults
    - Reads user config from configs/app.json, merges over defaults
    - Validates required fields

    Returns:
        Merged configuration dict.
    """
    # 1. Load defaults
    default_path = os.path.join(DEFAULTS_DIR, CONFIG_FILE)
    try:
        with open(default_path) as f:
            defaults = json.load(f)
    except FileNotFoundError:
        logger.warning("Default config not found at %s, using empty defaults", default_path)
        defaults = {}

    # 2. Ensure user config exists
    user_path = os.path.join(config_dir, CONFIG_FILE)
    if not os.path.exists(user_path):
        try:
            os.makedirs(config_dir, exist_ok=True)
            shutil.copy2(default_path, user_path)
            logger.warning(
                "Created %s from default. Edit it to configure the gateway.",
                user_path,
            )
        except Exception as e:
            logger.warning("Failed to create %s: %s", user_path, e)

    # 3. Load user config
    user_config = {}
    if os.path.exists(user_path):
        try:
            with open(user_path) as f:
                user_config = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("Failed to load %s: %s. Using defaults.", user_path, e)

    # 4. Merge (shallow merge at top level)
    merged = dict(defaults)
    for key, value in user_config.items():
        if isinstance(value, dict) and key in merged and isinstance(merged[key], dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value

    # 5. Validate
    _validate_config(merged)

    return merged


def _validate_config(config: dict[str, Any]) -> None:
    """Validates required fields and logs warnings for missing ones."""
    valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

    logging_cfg = config.get("logging", {})
    level = logging_cfg.get("level", "INFO")
    if level not in valid_levels:
        logger.warning(
            "Invalid logging.level '%s' in config. Must be one of %s. Using 'INFO'.",
            level, sorted(valid_levels),
        )
        logging_cfg["level"] = "INFO"

    request_id_cfg = config.get("request_id", {})
    if not isinstance(request_id_cfg.get("header", "X-Request-ID"), str):
        logger.warning("request_id.header must be a string. Using 'X-Request-ID'.")
