"""
Registries for the declarative API Gateway.

Contains:
- ServiceRegistry and ServiceClient — HTTP clients for backend services
- Registry — generic registry for pluggable components (access handlers, response handlers, auth strategies)
"""

from __future__ import annotations

from typing import Any, Callable, Optional

import httpx


class ServiceClient:
    """HTTP client for a single backend service."""

    def __init__(self, base_url: str, timeout: int = 30):
        base = base_url.rstrip("/")
        self.base_url = base
        self._sync_client = httpx.Client(
            base_url=base,
            timeout=httpx.Timeout(timeout),
        )
        self._async_client = httpx.AsyncClient(
            base_url=base,
            timeout=httpx.Timeout(timeout),
        )

    # ── Synchronous methods (backwards compatible) ──

    def request(self, method: str, path: str, **kwargs) -> httpx.Response:
        return self._sync_client.request(method, path, **kwargs)

    def get(self, path: str, **kwargs) -> httpx.Response:
        return self._sync_client.request("GET", path, **kwargs)

    def post(self, path: str, **kwargs) -> httpx.Response:
        return self._sync_client.request("POST", path, **kwargs)

    def put(self, path: str, **kwargs) -> httpx.Response:
        return self._sync_client.request("PUT", path, **kwargs)

    def patch(self, path: str, **kwargs) -> httpx.Response:
        return self._sync_client.request("PATCH", path, **kwargs)

    def delete(self, path: str, **kwargs) -> httpx.Response:
        return self._sync_client.request("DELETE", path, **kwargs)

    # ── Async methods (for use in async handlers / engine) ──

    async def request_async(self, method: str, path: str, **kwargs) -> httpx.Response:
        return await self._async_client.request(method, path, **kwargs)

    async def get_async(self, path: str, **kwargs) -> httpx.Response:
        return await self._async_client.request("GET", path, **kwargs)

    async def post_async(self, path: str, **kwargs) -> httpx.Response:
        return await self._async_client.request("POST", path, **kwargs)

    async def put_async(self, path: str, **kwargs) -> httpx.Response:
        return await self._async_client.request("PUT", path, **kwargs)

    async def patch_async(self, path: str, **kwargs) -> httpx.Response:
        return await self._async_client.request("PATCH", path, **kwargs)

    async def delete_async(self, path: str, **kwargs) -> httpx.Response:
        return await self._async_client.request("DELETE", path, **kwargs)

    async def close(self):
        await self._async_client.aclose()
        self._sync_client.close()


class ServiceRegistry:
    """
    Registry of HTTP clients for backend services.

    Allows access to services via attributes:
    ctx.services.users.get("/profiles/1")
    """

    def __init__(self, services: dict[str, dict]):
        self._services: dict[str, ServiceClient] = {}
        for name, cfg in services.items():
            self._services[name] = ServiceClient(
                cfg["base_url"],
                cfg.get("timeout", 30)
            )

    def __getattr__(self, name: str) -> ServiceClient:
        if name.startswith("_"):
            raise AttributeError(name)
        if name not in self._services:
            raise KeyError(f"Unknown service: {name}")
        return self._services[name]

    def get_client(self, name: str) -> Optional[ServiceClient]:
        """Get a service client by name (no exception)."""
        return self._services.get(name)

    async def close_all(self):
        for client in self._services.values():
            await client.close()


class Registry:
    """
    Generic registry for pluggable components.

    Supports registering components via decorator and retrieving by name.
    """

    def __init__(self):
        self._items: dict[str, Callable] = {}

    def register(self, name: str):
        """Decorator to register a component."""
        def decorator(fn):
            self._items[name] = fn
            return fn
        return decorator

    def get(self, name: str) -> Optional[Callable]:
        """Get a component by name."""
        return self._items.get(name)

    def has(self, name: str) -> bool:
        """Check if a component with this name is registered."""
        return name in self._items

    def create(self, name: str, config: Any) -> Optional[Callable]:
        """For auth strategies: create an instance from a factory."""
        factory = self._items.get(name)
        if factory is None:
            return None
        return factory(config)


# Global registry instances
access_handler_registry = Registry()
response_handler_registry = Registry()
auth_strategy_registry = Registry()

# Convenience decorators
register_access_handler = access_handler_registry.register
register_response_handler = response_handler_registry.register
register_auth_strategy = auth_strategy_registry.register

# Pre-request handler registry
pre_request_handler_registry = Registry()
register_pre_request_handler = pre_request_handler_registry.register
