#!/usr/bin/env python3
"""
Configuration validator for PyApiGate.

Checks that configs/app.json and configs/routes.yaml exist,
creates them from defaults if missing, and validates required fields.

Usage:
    python scripts/validate_config.py
"""

import json
import os
import sys
import shutil

DEFAULTS_DIR = "configs_default"
CONFIG_DIR = "configs"
FILES = {
    "app.json": "Application configuration",
    "routes.yaml": "Route definitions",
}

ERRORS = 0
WARNINGS = 0


def check_file(name: str, description: str) -> None:
    global ERRORS, WARNINGS

    config_path = os.path.join(CONFIG_DIR, name)
    default_path = os.path.join(DEFAULTS_DIR, name)

    # Check if config file exists
    if not os.path.exists(config_path):
        # Try to create from default
        if os.path.exists(default_path):
            try:
                os.makedirs(CONFIG_DIR, exist_ok=True)
                shutil.copy2(default_path, config_path)
                WARNINGS += 1
                print(f"  \u26a0  Created {config_path} from default template. Edit it before running the gateway.")
            except (IOError, OSError) as e:
                ERRORS += 1
                print(f"  \u2716  Failed to create {config_path}: {e}")
        else:
            ERRORS += 1
            print(f"  \u2716  {config_path} not found and no default template at {default_path}")
        return

    print(f"  \u2713  {config_path} exists ({description})")

    # Validate JSON structure for app.json
    if name == "app.json":
        try:
            with open(config_path) as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            ERRORS += 1
            print(f"  \u2716  {config_path}: invalid JSON \u2014 {e}")
            return

        # Check logging section
        logging_cfg = data.get("logging")
        if logging_cfg is None:
            WARNINGS += 1
            print(f"  \u26a0  {config_path}: missing 'logging' section")
        else:
            level = logging_cfg.get("level", "INFO")
            valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
            if level not in valid_levels:
                WARNINGS += 1
                print(f"  \u26a0  {config_path}: logging.level '{level}' invalid. Must be one of {sorted(valid_levels)}")

        # Check request_id section
        request_id_cfg = data.get("request_id")
        if request_id_cfg is None:
            WARNINGS += 1
            print(f"  \u26a0  {config_path}: missing 'request_id' section")

    # Validate YAML for routes.yaml
    if name == "routes.yaml":
        try:
            import yaml
            with open(config_path) as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict) or "routes" not in data:
                WARNINGS += 1
                print(f"  \u26a0  {config_path}: missing 'routes' key")
        except Exception as e:
            ERRORS += 1
            print(f"  \u2716  {config_path}: invalid YAML \u2014 {e}")


def main():
    global ERRORS, WARNINGS

    print(f"PyApiGate Configuration Check")
    print(f"==============================")
    print()

    # Check directories
    if not os.path.isdir(DEFAULTS_DIR):
        ERRORS += 1
        print(f"  \u2716  Defaults directory '{DEFAULTS_DIR}' not found. Is this the project root?")
        print()
        print(f"  Result: FAILED ({ERRORS} error(s), {WARNINGS} warning(s))")
        sys.exit(1)

    if not os.path.isdir(CONFIG_DIR):
        WARNINGS += 1
        print(f"  \u26a0  Config directory '{CONFIG_DIR}' not found. It will be created on first run.")

    # Check each file
    for name, description in FILES.items():
        check_file(name, description)

    # Summary
    print()
    if ERRORS == 0 and WARNINGS == 0:
        print("  Result: OK \u2014 all configurations are valid.")
        sys.exit(0)
    elif ERRORS == 0:
        print(f"  Result: OK ({WARNINGS} warning(s)) \u2014 review warnings above.")
        sys.exit(0)
    else:
        print(f"  Result: FAILED ({ERRORS} error(s), {WARNINGS} warning(s)) \u2014 fix errors above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
