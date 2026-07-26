"""
Flask app factory для PyApiGate.
"""
from __future__ import annotations

import os
from typing import Optional

from flask import Flask


def create_app(
    config_path: Optional[str] = None,
    import_handlers: bool = True,
    base_path: Optional[str] = None,
) -> Flask:
    """
    Создаёт и настраивает Flask-приложение с декларативным engine.

    Args:
        config_path: Путь к routes.yaml. Если None — ищет routes.yaml в CWD.
        import_handlers: Автоматически импортировать хендлеры.
        base_path: Если задан, переопределяет base_path из YAML.

    Returns:
        Настроенное Flask-приложение.
    """
    application = Flask(__name__)
    application.config['JSON_AS_ASCII'] = False

    from flask import json
    json.provider.DefaultJSONProvider.ensure_ascii = False

    from app.engine.bootstrap import bootstrap
    config = bootstrap(
        application,
        config_path=config_path,
        import_handlers=import_handlers,
    )

    return application
