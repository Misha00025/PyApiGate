"""
FastAPI app factory for PyApiGate.
"""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI

import handlers  # noqa: F401 — register custom handlers


def create_app(
    config_path: Optional[str] = None,
) -> FastAPI:
    """
    Creates and configures a FastAPI application with the declarative engine.

    Args:
        config_path: Path to routes.yaml. If None — looks for configs/routes.yaml.

    Returns:
        Configured FastAPI application.
    """
    # Initialize configuration and logging first
    from app.config import load_app_config
    from app.logging_config import setup_logging

    app_cfg = load_app_config()
    setup_logging(app_cfg)

    application = FastAPI(title="PyApiGate")

    from app.engine.bootstrap import bootstrap
    bootstrap(
        application,
        config_path=config_path,
    )

    return application
