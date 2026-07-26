"""
Pipeline for processing requests in the declarative API Gateway.

Processing order:
1. Auth — invoke AuthStrategy (passed from outside)
2. Access — invoke access handler (if specified)
3. Execute — proxy to backend or invoke response handler
"""

from __future__ import annotations

from typing import Optional

from flask import Response as FlaskResponse

from app.engine.context import RouteContext
from app.engine.models import AuthStrategy, RouteConfig
from app.engine.registry import (
    access_handler_registry,
    response_handler_registry,
)
from app.engine.status import (
    bad_gateway, forbidden, not_implemented, unauthorized,
)


def execute_pipeline(
    route: RouteConfig,
    ctx: RouteContext,
    auth_strategy: AuthStrategy = None,
) -> FlaskResponse:
    """
    Executes the full request processing pipeline.

    Args:
        route: Route configuration.
        ctx: Request context.
        auth_strategy: Authentication function (optional).
    """
    # Step 1: Auth
    if route.auth == "required":
        if auth_strategy is None:
            return not_implemented("Auth is required but no auth_strategy provided")

        payload = auth_strategy(ctx)
        if payload is None:
            return unauthorized("Invalid or expired token")

        ctx.jwt = payload

    # Step 2: Access
    access_name = route.access
    if access_name:
        handler = access_handler_registry.get(access_name)
        if handler is None:
            return not_implemented(f"Unknown access handler: {access_name}")

        result = handler(ctx)
        if not result.allowed:
            return result.response if result.response else forbidden()

    # Step 3: Execute (Proxy or Handler)
    if route.handler is not None:
        handler = response_handler_registry.get(route.handler)
        if handler is None:
            return not_implemented(f"Unknown response handler: {route.handler}")
        response = handler(ctx)
    else:
        from app.engine.proxy import execute_proxy
        response = execute_proxy(route, ctx)

    return response
