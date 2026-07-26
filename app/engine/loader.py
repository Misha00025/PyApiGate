"""
Parsing YAML configuration into GatewayConfig models.

Supports:
- Services section
- Routes section with single-method and multi-method normalization
- ProxyConfig, ParamsConfig, RouteConfig
"""

from __future__ import annotations

import os
import re
from typing import Any, Optional

import yaml

from app.engine.models import (
    AuthConfig,
    GatewayConfig,
    ParamsConfig,
    ProxyConfig,
    RouteConfig,
    ServiceConfig,
)


def load_config(path: Optional[str] = None) -> GatewayConfig:
    """
    Loads and parses YAML route configuration.

    Args:
        path: Path to YAML file. If None — looks for routes.yaml in the service root.

    Returns:
        GatewayConfig with parsed services and routes.
    """
    if path is None:
        path = "routes.yaml"

    with open(path) as f:
        raw = yaml.safe_load(f)

    return _parse_config(raw)


def _resolve_env_vars(value: str) -> str:
    """Substitutes environment variables in ${VAR} or ${VAR:-default} format."""
    def _replace(match):
        var_name = match.group(1)
        raw_default = match.group(2)
        default = raw_default.lstrip("-") if raw_default else None
        val = os.environ.get(var_name)
        if val is None:
            if default is not None:
                return default
            raise ValueError(
                f"Environment variable '{var_name}' is required "
                f"but not set (in routes.yaml service base_url)"
            )
        return val
    return re.sub(r'\$\{([^:}]+)(?::([^}]*))?\}', _replace, value)


def _parse_config(raw: dict) -> GatewayConfig:
    """Parses raw YAML dict into GatewayConfig."""
    base_path = raw.get("base_path", "") or ""
    services_raw = raw.get("services", {}) or {}
    routes_raw = raw.get("routes", []) or []

    services = {}
    for name, cfg in services_raw.items():
        services[name] = ServiceConfig(
            base_url=_resolve_env_vars(cfg["base_url"]),
            timeout=cfg.get("timeout", 30),
        )

    routes = []
    for route_def in routes_raw:
        parsed_routes = _parse_route(route_def)
        routes.extend(parsed_routes)

    # Parse auth section
    auth_raw = raw.get("auth", {}) or {}
    if isinstance(auth_raw, dict):
        auth_config = AuthConfig(
            strategy=auth_raw.get("strategy", "none"),
            public_key_path=auth_raw.get("public_key_path"),
            expected_issuer=auth_raw.get("expected_issuer"),
        )
    else:
        auth_config = AuthConfig()

    return GatewayConfig(
        base_path=base_path,
        auth=auth_config,
        services=services,
        routes=routes,
    )


def _parse_route(route_def: dict) -> list[RouteConfig]:
    """
    Parses a single YAML route block into one or more RouteConfig.

    Supports:
    - Simple format: method + proxy/handler
    - Multi-method format: methods: {GET: ..., POST: ...}
    - List methods: [GET, POST] with shared access/proxy
    """
    path = route_def["path"]

    # Multi-method format (methods is a dict)
    if "methods" in route_def and isinstance(route_def["methods"], dict):
        result = []
        for method, method_cfg in route_def["methods"].items():
            merged = dict(route_def)
            merged.pop("methods", None)
            merged.update(method_cfg)
            merged["method"] = method
            result.extend(_parse_single_route(path, merged))
        return result

    # List methods: [GET, POST] — one config for all
    methods = route_def.get("methods")
    if isinstance(methods, list):
        result = []
        for method in methods:
            single_def = dict(route_def)
            single_def["method"] = method
            result.extend(_parse_single_route(path, single_def))
        return result

    # Single method
    return _parse_single_route(path, route_def)


def _parse_single_route(path: str, route_def: dict) -> list[RouteConfig]:
    """Parses a single route with one HTTP method."""
    methods = [route_def.pop("method", "GET")]

    auth = route_def.get("auth", "required")
    access = route_def.get("access")
    description = route_def.get("description")

    # Proxy
    proxy = None
    if "proxy" in route_def:
        proxy_raw = route_def["proxy"]
        proxy = ProxyConfig(
            service=proxy_raw["service"],
            path=proxy_raw.get("path", path),
            skip_body=proxy_raw.get("skip_body", False),
            headers=proxy_raw.get("headers", {}),
        )

    # Handler
    handler = route_def.get("handler")

    # Params
    params = None
    if "params" in route_def:
        params_raw = route_def["params"]
        params = ParamsConfig(
            query=params_raw.get("query"),
            body=params_raw.get("body"),
        )

    return [
        RouteConfig(
            path=path,
            methods=methods,
            auth=auth,
            access=access,
            proxy=proxy,
            handler=handler,
            params=params,
            description=description,
        )
    ]
