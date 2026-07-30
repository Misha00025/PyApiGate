"""
Data models for the declarative API Gateway.

Contains dataclasses for routes, proxy configuration,
parameters, and services.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional


AuthStrategy = Callable[["RouteContext"], Optional[dict]]


@dataclass
class ProxyConfig:
    """Proxy request settings to a backend service."""
    service: str
    """Service name from the services section."""
    path: str
    """Target path in the backend service (may contain {placeholders})."""
    skip_body: bool = False
    """Do not forward the request body (e.g. for PUT without body)."""
    headers: dict[str, str] = field(default_factory=dict)
    """Extra headers for the proxy request."""


@dataclass
class ParamsConfig:
    """Parameter injection settings for backend requests."""
    query: Optional[dict[str, str] | str | list] = None
    """
    Query string parameters.
    Can be:
    - "*" — forward all incoming query params as-is
    - ["*", {"dest": "source"}] — forward all + additional mappings
    - {"dest": "source"} — parameter mapping
      source format: "{jwt.field}", "{path.field}", "{query.field}" or literal
    """
    body: Optional[dict[str, str]] = None
    """
    JSON body parameters (body injection).
    {"dest": "{jwt.userId}"} — inserts userId from JWT into body.
    """


@dataclass
class ResponseConfig:
    """Response wrapping configuration."""
    wrap: Optional[str] = None
    """Key name to wrap the JSON response in."""


@dataclass
class RouteConfig:
    """Configuration for a single route."""
    path: str
    """Flask-compatible path (e.g. /users/<int:user_id>/items)."""
    methods: list[str] = field(default_factory=lambda: ["GET"])
    """HTTP methods served by this route."""
    auth: str = "required"
    """Authorization requirement: "none" or "required"."""
    access: Optional[str] = None
    """
    Access handler name for permission checks.
    """
    proxy: Optional[ProxyConfig] = None
    """Proxy configuration (if the route type is PROXY)."""
    response_handler: Optional[str] = None
    """Response handler name, called after proxy execution to modify backend response."""
    handler: Optional[str] = None
    """Response handler name (if the route type is HANDLER)."""
    params: Optional[ParamsConfig] = None
    """Parameter injection settings."""
    response: Optional[ResponseConfig] = None
    """Response wrapping configuration."""
    description: Optional[str] = None
    """Route description (for documentation)."""


@dataclass
class ServiceConfig:
    """Backend service configuration."""
    base_url: str
    """Base URL of the service (e.g. http://my-api:8000)."""
    timeout: int = 30
    """HTTP request timeout in seconds."""


@dataclass
class AuthConfig:
    """Auth strategy configuration from YAML."""
    strategy: str = "none"
    """Strategy name (rsa_jwt, oauth2_jwt, none, or custom)."""
    public_key_path: Optional[str] = None
    """Path to RSA public key PEM file (for rsa_jwt)."""
    expected_issuer: Optional[str] = None
    """Expected iss claim in JWT (optional)."""
    jwks_url: Optional[str] = None
    """URL to JWKS endpoint (for oauth2_jwt strategy)."""


@dataclass
class GatewayConfig:
    """Root configuration of the API Gateway."""
    base_path: str = ""
    """URL prefix for all routes (e.g. /v2 or empty string /)."""
    auth: AuthConfig = field(default_factory=AuthConfig)
    """Auth strategy configuration."""
    services: dict[str, ServiceConfig] = field(default_factory=dict)
    """Backend services dict {name: config}."""
    routes: list[RouteConfig] = field(default_factory=list)
    """List of routes."""
