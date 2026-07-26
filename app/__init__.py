"""
Flask app factory for PyApiGate.
"""
from __future__ import annotations

import os
from typing import Optional

from flask import Flask


def create_app(
    config_path: Optional[str] = None,
) -> Flask:
    """
    Creates and configures a Flask application with the declarative engine.

    Args:
        config_path: Path to routes.yaml. If None — looks for routes.yaml in CWD.

    Returns:
        Configured Flask application.
    """
    application = Flask(__name__)

    from flask import json
    json.provider.DefaultJSONProvider.ensure_ascii = False

    from app.engine.bootstrap import bootstrap
    config = bootstrap(
        application,
        config_path=config_path,
    )

    return application
