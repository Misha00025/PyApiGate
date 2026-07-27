"""
Pipeline for processing requests in the declarative API Gateway.

Processing order:
1. Auth — invoke AuthStrategy (passed from outside)
2. Access — invoke access handler (if specified)
3. Execute — proxy to backend or invoke response handler
"""

from __future__ import annotations

import json
from typing import Optional

from starlette.responses import Response

from app.engine.context import RouteContext
from app.engine.models import AuthStrategy, RouteConfig
from app.engine.registry import (
    access_handler_registry,
    response_handler_registry,
)
from app.engine.status import (
    bad_gateway, forbidden, not_implemented, unauthorized,
)


async def execute_pipeline(
    route: RouteConfig,
    ctx: RouteContext,
    auth_strategy: AuthStrategy = None,
    ) -> Response:
    """
    Executes the full request processing pipeline.

    Args:
        route: Route configuration.
        ctx: Request context.
        auth_strategy: Authentication function (optional).
    """
    # Step 1: Auth (sync)
    if route.auth == "required":
        if auth_strategy is None:
            return not_implemented("Auth is required but no auth_strategy provided")

        payload = auth_strategy(ctx)
        if payload is None:
            return unauthorized("Invalid or expired token")

        ctx.jwt = payload

    # Pre-read body for backward compat (ctx.state["body"])
    content_type = ctx.request.headers.get("content-type", "")
    if "json" in content_type:
        try:
            ctx.state["body"] = await ctx.request.json()
        except Exception:
            ctx.state["body"] = None
    elif "text" in content_type or "xml" in content_type:
        try:
            body = await ctx.request.body()
            ctx.state["body"] = body.decode("utf-8")
        except Exception:
            ctx.state["body"] = None
    else:
        ctx.state["body"] = None

    # Step 2: Access (sync)
    access_name = route.access
    if access_name:
        handler = access_handler_registry.get(access_name)
        if handler is None:
            return not_implemented(f"Unknown access handler: {access_name}")

        result = handler(ctx)
        if not result.allowed:
            return result.response if result.response else forbidden()

    # Step 3: Execute (async)
    if route.handler is not None:
        handler = response_handler_registry.get(route.handler)
        if handler is None:
            return not_implemented(f"Unknown response handler: {route.handler}")
        response = await handler(ctx)
    else:
        from app.engine.proxy import execute_proxy
        response = await execute_proxy(route, ctx)

    # Step 3.5: Response wrapping (sync)
    if route.response and route.response.wrap:
        from fastapi.responses import JSONResponse
        try:
            data = json.loads(response.body)
        except Exception:
            data = response.body
        response = JSONResponse(
            content={route.response.wrap: data},
            status_code=response.status_code,
        )

    return response
