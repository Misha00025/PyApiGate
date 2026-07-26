"""
FastAPI app factory for PyApiGate.
"""
from __future__ import annotations

from typing import Optional

from fastapi import FastAPI


def create_app(
    config_path: Optional[str] = None,
) -> FastAPI:
    """
    Creates and configures a FastAPI application with the declarative engine.

    Args:
        config_path: Path to routes.yaml. If None — looks for routes.yaml in CWD.

    Returns:
        Configured FastAPI application.
    """
    application = FastAPI(title="PyApiGate")

    from app.engine.bootstrap import bootstrap
    config = bootstrap(
        application,
        config_path=config_path,
    )

    return application
