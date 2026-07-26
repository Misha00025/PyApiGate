"""
Pipeline обработки запроса в декларативном API Gateway.

Порядок обработки:
1. Auth — вызов AuthStrategy (переданной извне)
2. Access — вызов access-хендлера (если указан)
3. Execute — прокси в бэкенд или вызов response-хендлера
4. Response Transform — пост-обработка ответа
"""

from __future__ import annotations

from typing import Callable, Optional

from flask import Response as FlaskResponse

from app.engine.context import RouteContext
from app.engine.models import ResponseConfig, RouteConfig
from app.engine.registry import (
    access_handler_registry,
    response_handler_registry,
)

# Тип для стратегии аутентификации
AuthStrategy = Callable[[RouteContext], Optional[dict]]
"""
AuthStrategy — функция, которая принимает RouteContext и возвращает:
- dict (decoded JWT payload) — аутентификация пройдена
- None — аутентификация не пройдена (401)
"""


def execute_pipeline(
    route: RouteConfig,
    ctx: RouteContext,
    auth_strategy: AuthStrategy = None,
) -> FlaskResponse:
    """
    Выполняет полный pipeline обработки запроса.

    Args:
        route: Конфигурация маршрута.
        ctx: Контекст запроса.
        auth_strategy: Функция аутентификации (optional).
    """
    # Step 1: Auth
    if route.auth == "required":
        if auth_strategy is None:
            from app.engine.status import not_implemented
            return not_implemented("Auth is required but no auth_strategy provided")

        payload = auth_strategy(ctx)
        if payload is None:
            from app.engine.status import unauthorized
            return unauthorized("Invalid or expired token")

        ctx.jwt = payload

    # Step 2: Access
    access_name = route.get_access_handler(ctx.request.method)
    if access_name:
        handler = access_handler_registry.get(access_name)
        if handler is None:
            from app.engine.status import not_implemented
            return not_implemented(f"Unknown access handler: {access_name}")

        result = handler(ctx)
        if not result.allowed:
            return result.response if result.response else _default_forbidden()

    # Step 3: Execute (Proxy or Handler)
    if route.route_type.value == "handler":
        handler = response_handler_registry.get(route.handler)
        if handler is None:
            from app.engine.status import not_implemented
            return not_implemented(f"Unknown response handler: {route.handler}")
        response = handler(ctx)
    else:
        from app.engine.proxy import execute_proxy
        response = execute_proxy(route, ctx)

    # Step 4: Response Transform
    if route.response:
        response = apply_response_transform(route.response, response, ctx)

    return response


def _default_forbidden() -> FlaskResponse:
    from app.engine.status import forbidden
    return forbidden()


def apply_response_transform(
    response_cfg: ResponseConfig,
    response: FlaskResponse,
    ctx: RouteContext,
) -> FlaskResponse:
    """Применяет response-трансформацию к ответу."""
    from flask import jsonify
    from app.engine.registry import response_transform_registry

    try:
        data = response.get_json()
    except Exception:
        data = None

    if response_cfg.wrap and data is not None:
        data = {response_cfg.wrap: data}

    if response_cfg.handler:
        transform_fn = response_transform_registry.get(response_cfg.handler)
        if transform_fn:
            data = transform_fn(data, ctx)

    if data is not None:
        new_response = jsonify(data)
        new_response.status_code = response.status_code
        for key, value in response.headers.items():
            if key.lower() not in ("content-type", "content-length"):
                new_response.headers[key] = value
        return new_response

    return response
