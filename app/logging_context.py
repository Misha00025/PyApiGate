"""
Logging context for the API Gateway.

Allows per-request fields (jwt, path_params, query_params) to be injected
into log format via source expressions: {jwt.field}, {path.field}, {query.field}.
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any, Optional

from app.engine.context import RouteContext


class LoggingContext:
    """Holds request-scoped fields for log format resolution."""
    def __init__(self, ctx: RouteContext):
        self.jwt: Optional[dict[str, Any]] = ctx.jwt
        self.path_params: dict[str, Any] = ctx.path_params
        self.query_params: dict[str, Any] = dict(ctx.request.query_params)


_logging_context: ContextVar[Optional[LoggingContext]] = ContextVar("logging_context", default=None)


def set_logging_context(ctx: RouteContext) -> None:
    """Set the logging context for the current request."""
    _logging_context.set(LoggingContext(ctx))


def clear_logging_context() -> None:
    """Clear the logging context for the current request."""
    _logging_context.set(None)


def resolve_source(expr: str) -> str:
    """
    Resolve a source expression to a string value.

    Supported formats:
    - "{jwt.field}" — from JWT payload
    - "{path.field}" — from path parameters
    - "{query.field}" — from request query parameters
    - Anything else — returned as-is

    If source is missing or context is not set, returns "-".
    """
    if _is_source_expr(expr):
        log_ctx = _logging_context.get()
        if log_ctx is None:
            return "-"
        inner = expr[1:-1]
        source, key = inner.split(".", 1)
        if source == "jwt":
            value = log_ctx.jwt.get(key) if log_ctx.jwt else None
        elif source == "path":
            value = log_ctx.path_params.get(key)
        elif source == "query":
            value = log_ctx.query_params.get(key)
        else:
            return expr
        return str(value) if value is not None else "-"
    return expr


def _is_source_expr(expr: str) -> bool:
    """Check if expression looks like {source.field}."""
    if not (expr.startswith("{") and expr.endswith("}")):
        return False
    inner = expr[1:-1]
    if "." not in inner:
        return False
    source, _ = inner.split(".", 1)
    return source in ("jwt", "path", "query")
