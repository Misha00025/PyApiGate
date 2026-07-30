"""
Pipeline for processing requests in the declarative API Gateway.

Processing order:
1. Auth — invoke AuthStrategy (passed from outside)
2. Access — invoke access handler (if specified)
3. Execute — proxy to backend or invoke response handler
3b. Response Handler — invoke registered handler on proxy response (if specified)
4. Wrap — wrap response body in a key (if configured)
5. Log — log the request result
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Optional

from starlette.responses import Response

from app.engine.context import RouteContext
from app.engine.models import AuthStrategy, RouteConfig
from app.engine.proxy_response import ResponseBuilder
from app.engine.registry import (
    access_handler_registry,
    response_handler_registry,
)
from app.engine.status import (
    bad_gateway, forbidden, not_implemented, unauthorized,
)

logger = logging.getLogger(__name__)


async def execute_pipeline(
    route: RouteConfig,
    ctx: RouteContext,
    auth_strategy: AuthStrategy = None,
    ) -> Response:
    """
    Executes the full request processing pipeline.
    """
    # Request ID for tracing
    req_id = ctx.request.headers.get("X-Request-ID") or str(uuid.uuid4())
    ctx.state["request_id"] = req_id

    from app.logging_context import set_logging_context, clear_logging_context
    set_logging_context(ctx)

    # Initialize response builder — available to all handlers for modifications
    ctx.response = ResponseBuilder()

    try:
        start = time.monotonic()
        method = ctx.request.method
        path = str(ctx.request.url.path)

        # Step 1: Auth (sync)
        if route.auth == "required":
            if auth_strategy is None:
                logger.warning("No auth_strategy provided for required auth: %s %s [%s]", method, path, req_id)
                return not_implemented("Auth is required but no auth_strategy provided")

            payload = auth_strategy(ctx)
            if payload is None:
                logger.warning("Auth failed: %s %s [%s]", method, path, req_id)
                return unauthorized("Invalid or expired token")

            ctx.jwt = payload
            set_logging_context(ctx)
            logger.debug("Auth OK: %s %s user=%s [%s]", method, path, payload.get("sub", "?"), req_id)

        await ctx.request.load_body()

        # Step 2: Access (sync)
        access_name = route.access
        if access_name:
            handler = access_handler_registry.get(access_name)
            if handler is None:
                logger.error("Unknown access handler '%s': %s %s [%s]", access_name, method, path, req_id)
                return not_implemented(f"Unknown access handler: {access_name}")

            try:
                result = handler(ctx)
            except Exception:
                logger.exception("Access handler '%s' crashed: %s %s [%s]", access_name, method, path, req_id)
                return forbidden("Access handler error")

            if not result.allowed:
                elapsed = time.monotonic() - start
                logger.warning(
                    "Denied by '%s': %s %s [%s] (%.3fs)",
                    access_name, method, path, req_id, elapsed,
                )
                response = result.response if result.response else forbidden()
                response.headers["X-Deny-Reason"] = access_name
                return response

            logger.debug("Access OK by '%s': %s %s [%s]", access_name, method, path, req_id)

        # Step 3: Execute (async)
        try:
            if route.handler is not None:
                # Standard response handler
                handler = response_handler_registry.get(route.handler)
                if handler is None:
                    logger.error("Unknown response handler '%s': %s %s [%s]", route.handler, method, path, req_id)
                    return not_implemented(f"Unknown response handler: {route.handler}")
                response = await handler(ctx)
            elif route.response_handler is not None and route.proxy is not None:
                # Proxy route WITH response_handler
                from app.engine.proxy import _execute_proxy_raw

                handler = response_handler_registry.get(route.response_handler)
                if handler is None:
                    logger.error(
                        "Unknown response handler '%s': %s %s [%s]",
                        route.response_handler, method, path, req_id,
                    )
                    return not_implemented(f"Unknown response handler: {route.response_handler}")

                raw_resp = await _execute_proxy_raw(route, ctx)
                ctx.response.set_base(raw_resp)
                await handler(ctx)
                response = ctx.response.finalize()
            else:
                # Proxy route WITHOUT response_handler (or just proxy)
                from app.engine.proxy import execute_proxy
                response = await execute_proxy(route, ctx)
        except ValueError as e:
            return not_implemented(str(e))
        except Exception:
            logger.exception("Handler crashed: %s %s [%s]", method, path, req_id)
            return bad_gateway("Upstream error")

        # Step 3.5: Apply ResponseBuilder modifications (for non-finalized paths)
        if route.response_handler is None and not ctx.response.is_empty():
            response = ctx.response.apply_to(response)

        # Step 4: Response wrapping (sync)
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

        elapsed = time.monotonic() - start
        logger.info("%s %s -> %d [%s] (%.3fs)", method, path, response.status_code, req_id, elapsed)

        return response
    finally:
        clear_logging_context()
