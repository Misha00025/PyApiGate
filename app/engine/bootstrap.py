"""
Bootstrap — load YAML config and register routes in FastAPI.

Creates an APIRouter with routes from config, registers it in the FastAPI app.
"""

from __future__ import annotations

import logging
import re
from typing import Callable, Optional

from fastapi import APIRouter, FastAPI, Request

import app.auth_strategies  # noqa: F401 — triggers @register_auth_strategy decorators

from app.engine.context import GatewayRequest, RouteContext
from app.engine.loader import load_config
from app.engine.models import GatewayConfig, RouteConfig
from app.engine.pipeline import execute_pipeline
from app.engine.registry import ServiceRegistry, auth_strategy_registry

logger = logging.getLogger(__name__)


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
    # Healthcheck endpoint — no auth, no proxy, available at /health
    @app.get("/health", include_in_schema=False)
    async def _health():
        return {"status": "ok"}

    # Load config
    config = load_config(config_path)
    logger.info("Loaded %d routes from config", len(config.routes))

    # Create auth strategy from config

    if config.auth.strategy and config.auth.strategy != "none":
        strategy = auth_strategy_registry.create(config.auth.strategy, config.auth)
        if strategy is None:
            logger.warning("Unknown auth strategy '%s', auth disabled", config.auth.strategy)
        else:
            logger.info("Using auth strategy: %s", config.auth.strategy)
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
    logger.info("Registered services: %s", list(services_dict.keys()))

    # Create APIRouter
    bp_name = "engine_api"
    router = APIRouter(prefix=config.base_path or "")

    # Register each route
    for route in config.routes:
        _register_route(router, route, registry, strategy)

    # Register router in the app
    app.include_router(router)
    logger.info("Router '%s' registered at '%s'", bp_name, config.base_path or "/")

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
        async def view_func(request: Request):
            ctx = RouteContext(
                request=GatewayRequest(request),
                path_params=dict(request.path_params) if request.path_params else {},
                jwt=None,
                services=reg,
            )
            return await execute_pipeline(rc, ctx, auth_strategy=auth)
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
        logger.debug("  [Engine] %s %s%s", method.ljust(7), prefix, route.path)
