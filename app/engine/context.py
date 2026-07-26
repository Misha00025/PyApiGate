"""
Request context for the declarative API Gateway.

Contains RouteContext — the object passed through the pipeline
and available to all handlers (access and response).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from flask import Request


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
    - request: original Flask Request
    - path_params: parameters from URL (user_id, item_id, ...)
    - jwt: decoded JWT payload (or None)
    - services: registry of HTTP clients for backend services
    - state: mutable dict for passing data between pipeline stages

    Handlers use ctx.allow() and ctx.deny() to return results.
    """
    request: Request
    """Original Flask Request."""
    path_params: dict[str, Any]
    """Parameters from URL (user_id, item_id, ...)."""
    jwt: Optional[dict[str, Any]] = None
    """Decoded JWT payload (or None if auth=none)."""
    services: Any = None
    """ServiceRegistry with HTTP clients for backends."""
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
