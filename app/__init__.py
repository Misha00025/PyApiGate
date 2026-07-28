"""
FastAPI app factory for PyApiGate.
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import FastAPI

from app.config import CONFIG_DIR

import handlers  # noqa: F401 — register custom handlers


def create_app(
    config_path: Optional[str] = None,
) -> FastAPI:
    """
    Creates and configures a FastAPI application with the declarative engine.

    Args:
        config_path: Path to app.json. If None — uses APP_CONFIG env var,
                     then falls back to configs/app.json.

    Returns:
        Configured FastAPI application.
    """
    # Initialize configuration and logging first
    from app.config import load_app_config
    from app.logging_config import setup_logging

    if config_path is None:
        config_path = os.environ.get("APP_CONFIG")

    app_cfg = load_app_config(config_path)
    setup_logging(app_cfg)

    application = FastAPI(title="PyApiGate")

    # CORS middleware (optional)
    cors_cfg = app_cfg.get("cors")
    if isinstance(cors_cfg, dict):
        from starlette.middleware.cors import CORSMiddleware

        application.add_middleware(
            CORSMiddleware,
            allow_origins=cors_cfg.get("allow_origins", ["*"]),
            allow_methods=cors_cfg.get("allow_methods", ["*"]),
            allow_headers=cors_cfg.get("allow_headers", ["*"]),
            allow_credentials=cors_cfg.get("allow_credentials", False),
        )

    from app.engine.bootstrap import bootstrap

    # Determine which route config files to load
    route_files = app_cfg.get("routes", {}).get("files")
    if route_files is None:
        route_files = ["routes.yaml"]

    # Resolve relative paths relative to the app config directory
    if config_path:
        base_dir = os.path.dirname(config_path)
    else:
        base_dir = CONFIG_DIR

    config_paths = [
        os.path.join(base_dir, f) if not os.path.isabs(f) else f
        for f in route_files
    ]

    from app.engine.bootstrap import bootstrap
    bootstrap(application, config_paths=config_paths)

    return application
