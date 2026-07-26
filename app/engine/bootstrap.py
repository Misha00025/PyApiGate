"""
Bootstrap — load YAML config and register routes in FastAPI.

Creates an APIRouter with routes from config, registers it in the FastAPI app.
"""

from __future__ import annotations

import re
from typing import Callable, Optional

from fastapi import APIRouter, FastAPI, Request

from app.engine.context import RouteContext
from app.engine.loader import load_config
from app.engine.models import GatewayConfig, RouteConfig
from app.engine.pipeline import execute_pipeline
from app.engine.registry import ServiceRegistry, auth_strategy_registry


def bootstrap(
    app: FastAPI,
    config_path: Optional[str] = None,
) -> GatewayConfig:
    """
    Loads config and registers routes in the FastAPI application.

    Args:
        app: FastAPI application.
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

    # Create APIRouter
    bp_name = "engine_api"
    router = APIRouter(prefix=config.base_path or "")

    # Register each route
    for route in config.routes:
        _register_route(router, route, registry, strategy)

    # Register router in the app
    app.include_router(router)
    print(f"[Engine] Router '{bp_name}' registered at '{config.base_path or '/'}'")

    return config


def _register_route(
    router: APIRouter,
    route: RouteConfig,
    registry: ServiceRegistry,
    auth_strategy: Optional[Callable] = None,
) -> None:
    """Registers a single route in the APIRouter."""

    # Convert Flask URL patterns to FastAPI: <int:user_id> -> {user_id}
    fastapi_path = re.sub(r'<(?:\w+:)?(\w+)>', r'{\1}', route.path)

    def make_view_func(rc: RouteConfig, reg: ServiceRegistry, auth: Optional[Callable]):
        def view_func(request: Request):
            ctx = RouteContext(
                request=request,
                path_params=dict(request.path_params) if request.path_params else {},
                jwt=None,
                services=reg,
            )
            return execute_pipeline(rc, ctx, auth_strategy=auth)
        view_func.__name__ = f"engine_{rc.path.replace('/', '_').replace('<', '').replace('>', '').replace('.', '_')}"
        return view_func

    for method in route.methods:
        view_func = make_view_func(route, registry, auth_strategy)
        router.add_api_route(
            fastapi_path,
            endpoint=view_func,
            methods=[method],
            include_in_schema=False,
        )
        prefix = router.prefix or ""
        print(f"  [Engine] {method:7s} {prefix}{route.path}")
