"""
HTTP proxy for the declarative API Gateway.

Performs HTTP requests to backend services with parameter substitution
from path, query, body and JWT.
"""

from __future__ import annotations

from typing import Any, Optional

from fastapi.responses import JSONResponse
from starlette.responses import Response
import requests as http_requests

from app.engine.context import RouteContext
from app.engine.models import ParamsConfig, ProxyConfig, RouteConfig
from app.engine.status import bad_gateway, not_implemented
from app.security import get_user_id


async def execute_proxy(route: RouteConfig, ctx: RouteContext) -> Response:
    """
    Executes a proxy request to a backend service.

    1. Substitutes path_params into the target URL
    2. Injects query/body parameters
    3. Makes the HTTP request
    4. Returns a Flask Response with backend body and status

    Args:
        route: Route configuration.
        ctx: Request context with path_params, jwt, services.

    Returns:
        Flask Response.
    """
    proxy_cfg = route.proxy
    if proxy_cfg is None:
        return not_implemented("No proxy config")

    # 1. Substitute path_params into the target path
    target_path = _resolve_path(proxy_cfg.path, ctx.path_params)

    # 2. Get the service client
    client = ctx.services.get_client(proxy_cfg.service)
    if client is None:
        return not_implemented(f"Unknown service: {proxy_cfg.service}")

    # 3. Build request parameters
    method = ctx.request.method.lower()
    headers = _build_headers(ctx, proxy_cfg)
    params = _build_query_params(route, ctx)
    body = await _build_body(route, ctx)

    # 4. Execute the request
    try:
        if proxy_cfg.skip_body or method in ("get", "delete"):
            resp = client.request(
                method.upper(),
                target_path,
                headers=headers,
                params=params,
            )
        else:
            resp = client.request(
                method.upper(),
                target_path,
                headers=headers,
                params=params,
                json=body,
            )
    except http_requests.RequestException as e:
        return bad_gateway(f"Upstream error: {e}")

    # 5. Return the response
    return _to_response(resp)


def _resolve_path(template: str, path_params: dict[str, Any]) -> str:
    """Substitutes {placeholders} from path_params into the path template."""
    result = template
    for key, value in path_params.items():
        placeholder = "{" + key + "}"
        result = result.replace(placeholder, str(value))
    return result


def _build_headers(ctx: RouteContext, proxy_cfg: ProxyConfig) -> dict[str, str]:
    """Builds headers for the proxy request."""
    headers = {}
    for key, value in ctx.request.headers.items():
        if key.lower() not in ("host", "content-length", "content-type"):
            headers[key] = value
    headers.update(proxy_cfg.headers)
    return headers


def _build_query_params(route: RouteConfig, ctx: RouteContext) -> dict[str, Any]:
    """Builds query parameters for the proxy request."""
    params_cfg = route.params
    if params_cfg is None or params_cfg.query is None:
        return dict(ctx.request.query_params)

    if params_cfg.query == "*":
        result = dict(ctx.request.query_params)
        if ctx.jwt and get_user_id(ctx.jwt):
            result["userId"] = get_user_id(ctx.jwt)
        return result

    if isinstance(params_cfg.query, dict):
        result = {}
        for dest, source in params_cfg.query.items():
            if source == "*":
                for k, v in ctx.request.query_params.items():
                    if k not in result:
                        result[k] = v
            else:
                result[dest] = _resolve_source(source, ctx)
        return result

    return dict(ctx.request.query_params)


async def _build_body(route: RouteConfig, ctx: RouteContext) -> Optional[dict]:
    """Builds the body for the proxy request (body injection)."""
    params_cfg = route.params
    try:
        json_body = ctx.request.json
    except Exception:
        json_body = None
    if params_cfg is None or params_cfg.body is None:
        return json_body

    body = json_body or {}
    for dest, source in params_cfg.body.items():
        body[dest] = _resolve_source(source, ctx)
    return body


def _resolve_source(expr: str, ctx: RouteContext) -> Any:
    """
    Resolves a source expression to a value.

    Supported formats:
    - "{jwt.field}" — from JWT payload
    - "{path.field}" — from path parameters
    - "{query.field}" — from request query parameters
    - "literal" — returned as-is
    """
    if expr.startswith("{") and expr.endswith("}"):
        inner = expr[1:-1]
        if "." in inner:
            source, key = inner.split(".", 1)
            if source == "jwt":
                raw = ctx.jwt.get(key) if ctx.jwt else None
                if raw is None and key == "userId":
                    raw = ctx.jwt.get("sub") if ctx.jwt else None
                return raw
            elif source == "path":
                return ctx.path_params.get(key)
            elif source == "query":
                return ctx.request.query_params.get(key)
    return expr


def _to_response(resp: http_requests.Response) -> Response:
    """Converts a requests.Response to a Starlette Response."""
    content_type = resp.headers.get("Content-Type", "application/json")

    try:
        data = resp.json()
        return JSONResponse(content=data, status_code=resp.status_code)
    except (ValueError, TypeError):
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type=content_type,
        )
