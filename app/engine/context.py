"""
Request context for the declarative API Gateway.

Contains RouteContext — the object passed through the pipeline
and available to all handlers (access and response).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional

from fastapi import Request


class GatewayRequest:
    """
    Cached, framework-agnostic wrapper around the incoming FastAPI request.

    Caches body and JSON so they can be consumed multiple times
    (solves Starlette's single-consumption stream).
    """
    def __init__(self, req: Request):
        self._req = req
        self._cached_body: Optional[bytes] = None
        self._cached_json: Optional[Any] = None

    @property
    def method(self) -> str:
        return self._req.method

    @property
    def headers(self):
        return self._req.headers

    @property
    def query_params(self):
        return self._req.query_params

    @property
    def url(self):
        return self._req.url

    @property
    def path_params(self):
        return dict(self._req.path_params)

    async def load_body(self) -> None:
        """Load raw body from the stream into cache. Safe to call multiple times."""
        if self._cached_body is not None:
            return
        self._cached_body = await self._req.body()
        content_type = self._req.headers.get("content-type", "")
        if "json" in content_type:
            try:
                self._cached_json = json.loads(self._cached_body.decode("utf-8"))
            except (ValueError, TypeError, UnicodeDecodeError):
                self._cached_json = None

    @property
    def body(self) -> Optional[bytes]:
        """Cached raw request body. None if load_body() hasn't been called yet."""
        return self._cached_body

    @property
    def json(self) -> Optional[Any]:
        """Cached parsed JSON body. None if body isn't JSON or load_body() hasn't been called."""
        return self._cached_json

    @property
    def content_type(self) -> str:
        return self._req.headers.get("content-type", "").lower()

    @property
    def is_json(self) -> bool:
        return "json" in self.content_type


class AccessResult:
    """Result of an access handler check."""

    def __init__(self, allowed: bool, response=None):
        self.allowed = allowed
        self.response = response


@dataclass
class RouteContext:
    """
    Request context passed through the entire pipeline.

    Provides handlers with:
    - request: original GatewayRequest
    - path_params: parameters from URL (user_id, item_id, ...)
    - jwt: decoded JWT payload (or None)
    - services: registry of HTTP clients for backend services
    - state: mutable dict for passing data between pipeline stages

    Handlers use ctx.allow() and ctx.deny() to return results.
    """
    request: Request
    """Original GatewayRequest."""
    path_params: dict[str, Any]
    """Parameters from URL (user_id, item_id, ...)."""
    jwt: Optional[dict[str, Any]] = None
    """Decoded JWT payload (or None if auth=none)."""
    services: Any = None
    """ServiceRegistry with HTTP clients for backends."""
    response: Optional[Any] = None
    """ProxyResponseBuilder for modifying backend responses in response_handler."""
    state: dict[str, Any] = field(default_factory=dict)
    """Mutable storage for passing data between pipeline stages."""

    def allow(self) -> AccessResult:
        """Returns a positive access check result."""
        return AccessResult(allowed=True)

    def deny(self, response=None) -> AccessResult:
        """
        Returns a negative access check result.

        If response is not provided, a standard 403 Forbidden is used.
        """
        if response is None:
            from app.engine.status import forbidden
            response = forbidden()
        return AccessResult(allowed=False, response=response)
