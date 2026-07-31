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
    config_paths: Optional[list[str]] = None,
) -> tuple[list[GatewayConfig], list[ServiceRegistry]]:
    """
    Loads one or more YAML configs and registers routes in FastAPI.

    Each config file is self-contained (base_path, auth, services, routes).

    Args:
        app: FastAPI application.
        config_paths: List of paths to YAML files.

    Returns:
        Tuple of (loaded GatewayConfig objects, list of ServiceRegistry instances).
    """
    # Healthcheck — один на всё приложение
    @app.get("/health", include_in_schema=False)
    async def _health():
        return {"status": "ok"}

    loaded_configs = []
    all_registries = []

    for path in config_paths:
        logger.info("Loading config: %s", path)
        config = load_config(path)
        loaded_configs.append(config)

        # Auth strategy
        strategy = None
        if config.auth.strategy and config.auth.strategy != "none":
            strategy = auth_strategy_registry.create(config.auth.strategy, config.auth)
            if strategy is None:
                logger.warning("Unknown auth strategy '%s' in %s, auth disabled", config.auth.strategy, path)
            else:
                logger.info("  auth: %s", config.auth.strategy)
        else:
            logger.info("  auth: none")

        # ServiceRegistry
        services_dict = {}
        for name, svc in config.services.items():
            services_dict[name] = {
                "base_url": svc.base_url,
                "timeout": svc.timeout,
            }
        registry = ServiceRegistry(services_dict)
        all_registries.append(registry)
        logger.info("  services: %s", list(services_dict.keys()))

        # APIRouter со своим prefix
        router = APIRouter(prefix=config.base_path or "")

        for route in config.routes:
            _register_route(router, route, registry, strategy)

        app.include_router(router)
        logger.info("  registered %d routes at '%s'", len(config.routes), config.base_path or "/")

    return loaded_configs, all_registries


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
