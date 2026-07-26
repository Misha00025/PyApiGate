"""
Bootstrap — load YAML config and register routes in Flask.

Creates a Blueprint with routes from config, registers it in the Flask app.
"""

from __future__ import annotations

import os
from typing import Callable, Optional

from flask import Blueprint, Flask, request as flask_request

from app.engine.context import RouteContext
from app.engine.loader import load_config
from app.engine.models import GatewayConfig, RouteConfig
from app.engine.pipeline import execute_pipeline
from app.engine.registry import ServiceRegistry, auth_strategy_registry


def bootstrap(
    flask_app: Flask,
    config_path: Optional[str] = None,
) -> GatewayConfig:
    """
    Loads config and registers routes in the Flask application.

    Args:
        flask_app: Flask application.
        config_path: Path to YAML file. If None — looks for routes.yaml in the service root.

    Returns:
        GatewayConfig — loaded configuration.
    """
    # Load config
    config = load_config(config_path)
    print(f"[Engine] Loaded {len(config.routes)} routes from config")

    # Create auth strategy from config

    if config.auth.strategy and config.auth.strategy != "none":
        strategy = auth_strategy_registry.create(config.auth.strategy, config.auth)
        if strategy is None:
            print(f"[Engine] Warning: unknown auth strategy '{config.auth.strategy}', auth disabled")
        else:
            print(f"[Engine] Using auth strategy: {config.auth.strategy}")
    else:
        strategy = None

    # Create ServiceRegistry
    services_dict = {}
    for name, svc in config.services.items():
        services_dict[name] = {
            "base_url": svc.base_url,
            "timeout": svc.timeout,
        }
    registry = ServiceRegistry(services_dict)
    print(f"[Engine] Registered services: {list(services_dict.keys())}")

    # Create Blueprint
    bp_name = "engine_api"
    bp = Blueprint(bp_name, __name__, url_prefix=config.base_path or None)

    # Register each route
    for route in config.routes:
        _register_route(bp, route, registry, strategy)

    # Register Blueprint in the app
    flask_app.register_blueprint(bp)
    print(f"[Engine] Blueprint '{bp_name}' registered at '{config.base_path or '/'}'")

    return config


def _register_route(
    bp: Blueprint,
    route: RouteConfig,
    registry: ServiceRegistry,
    auth_strategy: Optional[Callable] = None,
) -> None:
    """Registers a single route in the Blueprint."""

    def make_view_func(rc: RouteConfig, reg: ServiceRegistry, auth: Optional[Callable]):
        def view_func(**path_params):
            ctx = RouteContext(
                request=flask_request,
                path_params=path_params,
                jwt=None,
                services=reg,
            )
            return execute_pipeline(rc, ctx, auth_strategy=auth)
        view_func.__name__ = f"engine_{rc.path.replace('/', '_').replace('<', '').replace('>', '').replace('.', '_')}"
        return view_func

    for method in route.methods:
        view_func = make_view_func(route, registry, auth_strategy)
        endpoint_name = f"{route.path}_{method}"
        endpoint_name = endpoint_name.replace(".", "_")
        bp.add_url_rule(
            route.path,
            endpoint=endpoint_name,
            view_func=view_func,
            methods=[method],
        )
        print(f"  [Engine] {method:7s} {bp.url_prefix}{route.path}")
