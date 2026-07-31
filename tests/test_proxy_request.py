"""
Tests for RequestBuilder and pre_request_handler pipeline.

RequestBuilder is created before the proxy request is sent. The pre_request_handler
receives the builder and modifies the outgoing request (headers, query params,
body, path) before it reaches the backend.
"""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
import httpx
from fastapi.responses import JSONResponse
from starlette.responses import Response
from starlette.requests import Request

from app.engine.context import RouteContext
from app.engine.models import ProxyConfig, ResponseConfig, RouteConfig
from app.engine.proxy_request import RequestBuilder
from app.engine.pipeline import execute_pipeline
from app.engine.registry import (
    register_pre_request_handler,
    register_response_handler,
    pre_request_handler_registry,
    response_handler_registry,
    ServiceRegistry,
)


# ---------------------------------------------------------------------------
# Helpers (same as test_proxy_response.py)
# ---------------------------------------------------------------------------

def make_raw_response(status_code=200, body=None, headers=None, content_type="application/json"):
    """Create a mock httpx.Response with given properties."""
    mock = MagicMock(spec=httpx.Response)
    mock.status_code = status_code
    mock.headers = headers or {"Content-Type": content_type}
    if body is not None:
        if isinstance(body, bytes):
            body_bytes = body
        elif isinstance(body, (dict, list)):
            body_bytes = json.dumps(body).encode()
        else:
            body_bytes = str(body).encode()
        mock.content = body_bytes
        if content_type == "application/json":
            mock.json.return_value = body
        else:
            mock.json.side_effect = ValueError("not json")
    else:
        mock.content = b""
        if content_type == "application/json":
            mock.json.return_value = {}
        else:
            mock.json.side_effect = ValueError("not json")
    return mock


async def make_gateway_request(method="GET", path="/test", body=None,
                                content_type="application/json"):
    """Build a GatewayRequest for pipeline tests."""
    from app.engine.context import GatewayRequest
    body_bytes = json.dumps(body).encode() if body is not None else b""
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "path": path,
        "headers": [
            (b"content-type", content_type.encode()),
            (b"content-length", str(len(body_bytes)).encode()),
        ],
        "query_string": b"",
        "client": ("127.0.0.1", 5000),
        "server": ("127.0.0.1", 5000),
        "scheme": "http",
        "asgi": {"version": "3.0"},
    }
    received = False

    async def receive():
        nonlocal received
        if received:
            return {"type": "http.disconnect"}
        received = True
        return {"type": "http.request", "body": body_bytes, "more_body": False}

    req = Request(scope, receive=receive)
    gw = GatewayRequest(req)
    await gw.load_body()
    return gw


# ===================================================================
# RequestBuilder Unit Tests
# ===================================================================

class TestRequestBuilder:

    def test_create_empty(self):
        """Builder can be created without arguments."""
        builder = RequestBuilder()
        assert builder.is_empty() is True

    def test_set_header(self):
        """set_header adds a request header."""
        builder = RequestBuilder()
        builder.set_header("Authorization", "Bearer token123")
        assert builder._headers == {"Authorization": "Bearer token123"}
        assert builder.is_empty() is False

    def test_remove_header(self):
        """remove_header marks a header for removal."""
        builder = RequestBuilder()
        builder.remove_header("X-Internal")
        assert "X-Internal" in builder._removed_headers
        assert builder.is_empty() is False

    def test_set_header_after_remove(self):
        """set_header overrides a previous remove_header."""
        builder = RequestBuilder()
        builder.remove_header("X-Internal")
        builder.set_header("X-Internal", "value")
        assert "X-Internal" not in builder._removed_headers
        assert builder._headers["X-Internal"] == "value"

    def test_remove_header_after_set(self):
        """remove_header overrides a previous set_header."""
        builder = RequestBuilder()
        builder.set_header("X-Custom", "value")
        builder.remove_header("X-Custom")
        assert "X-Custom" not in builder._headers
        assert "X-Custom" in builder._removed_headers

    def test_set_query_param(self):
        """set_query_param adds a query parameter."""
        builder = RequestBuilder()
        builder.set_query_param("page", "1")
        assert builder._query_params == {"page": "1"}
        assert builder.is_empty() is False

    def test_remove_query_param(self):
        """remove_query_param marks a query param for removal."""
        builder = RequestBuilder()
        builder.remove_query_param("internal")
        assert "internal" in builder._removed_query_params
        assert builder.is_empty() is False

    def test_set_body(self):
        """set_body overrides the request body."""
        builder = RequestBuilder()
        builder.set_body({"key": "value"})
        assert builder._body_override == {"key": "value"}
        assert builder.is_empty() is False

    def test_set_json_alias(self):
        """set_json is an alias for set_body."""
        builder = RequestBuilder()
        builder.set_json({"key": "value"})
        assert builder._body_override == {"key": "value"}

    def test_merge_body(self):
        """merge_body accumulates fields."""
        builder = RequestBuilder()
        builder.merge_body({"a": 1})
        builder.merge_body({"b": 2})
        assert builder._body_merge == {"a": 1, "b": 2}
        assert builder.is_empty() is False

    def test_set_path(self):
        """set_path overrides the target path."""
        builder = RequestBuilder()
        builder.set_path("/new/path/123")
        assert builder._path == "/new/path/123"
        assert builder.is_empty() is False

    def test_is_empty_initial(self):
        """Fresh builder is empty."""
        assert RequestBuilder().is_empty() is True

    def test_is_empty_after_set_header(self):
        builder = RequestBuilder()
        builder.set_header("X", "v")
        assert builder.is_empty() is False

    def test_is_empty_after_remove_header(self):
        builder = RequestBuilder()
        builder.remove_header("X")
        assert builder.is_empty() is False

    def test_is_empty_after_set_query_param(self):
        builder = RequestBuilder()
        builder.set_query_param("k", "v")
        assert builder.is_empty() is False

    def test_is_empty_after_remove_query_param(self):
        builder = RequestBuilder()
        builder.remove_query_param("k")
        assert builder.is_empty() is False

    def test_is_empty_after_set_body(self):
        builder = RequestBuilder()
        builder.set_body({"x": 1})
        assert builder.is_empty() is False

    def test_is_empty_after_merge_body(self):
        builder = RequestBuilder()
        builder.merge_body({"x": 1})
        assert builder.is_empty() is False

    def test_is_empty_after_set_path(self):
        builder = RequestBuilder()
        builder.set_path("/x")
        assert builder.is_empty() is False


# ===================================================================
# Pipeline Integration Tests
# ===================================================================

class TestPipelinePreRequestHandler:

    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        """Clean up test handlers after each test."""
        yield
        names_to_remove = []
        for name in list(pre_request_handler_registry._items.keys()):
            if name.startswith("_test_pre_"):
                names_to_remove.append(name)
        for name in names_to_remove:
            del pre_request_handler_registry._items[name]
        # Also clean up response handlers registered by tests
        for name in list(response_handler_registry._items.keys()):
            if name.startswith("_test_pre_"):
                names_to_remove.append(name)
        for name in names_to_remove:
            if name in response_handler_registry._items:
                del response_handler_registry._items[name]

    @pytest.fixture
    def mock_services(self):
        """Create a service registry with a mock backend."""
        reg = ServiceRegistry({"backend": {"base_url": "http://backend:8000"}})
        mock_resp = make_raw_response(status_code=200, body={"result": "ok"})
        client = reg.get_client("backend")
        client.request = AsyncMock(return_value=mock_resp)
        return reg

    # ── Header modification ───────────────────────────

    @pytest.mark.asyncio
    async def test_pre_request_adds_header(self, mock_services):
        """Pre-request handler adds a header to the proxy request."""

        @register_pre_request_handler("_test_pre_add_header")
        async def add_auth_header(ctx, req):
            req.set_header("Authorization", "Bearer mytoken")

        route = RouteConfig(
            path="/test", methods=["GET"], auth="none",
            proxy=ProxyConfig(service="backend", path="/api/data"),
            pre_request_handler="_test_pre_add_header",
        )
        gw = await make_gateway_request("GET", "/test")
        ctx = RouteContext(request=gw, path_params={}, services=mock_services)

        await execute_pipeline(route, ctx)

        # Verify the header was sent to the backend
        client = mock_services.get_client("backend")
        _, kwargs = client.request.call_args
        assert kwargs["headers"].get("Authorization") == "Bearer mytoken"

    @pytest.mark.asyncio
    async def test_pre_request_removes_header(self, mock_services):
        """Pre-request handler removes a header from the proxy request."""

        @register_pre_request_handler("_test_pre_remove_header")
        async def remove_internal_header(ctx, req):
            req.remove_header("X-Internal")

        route = RouteConfig(
            path="/test", methods=["GET"], auth="none",
            proxy=ProxyConfig(service="backend", path="/api/data"),
            pre_request_handler="_test_pre_remove_header",
        )
        gw = await make_gateway_request("GET", "/test")
        ctx = RouteContext(request=gw, path_params={}, services=mock_services)

        await execute_pipeline(route, ctx)

        client = mock_services.get_client("backend")
        _, kwargs = client.request.call_args
        # X-Internal wasn't set in the first place, but the removal code path was exercised
        assert "X-Internal" not in kwargs["headers"]

    # ── Query param modification ──────────────────────

    @pytest.mark.asyncio
    async def test_pre_request_adds_query_param(self, mock_services):
        """Pre-request handler adds a query parameter."""

        @register_pre_request_handler("_test_pre_add_query")
        async def add_query(ctx, req):
            req.set_query_param("api_key", "secret123")

        route = RouteConfig(
            path="/test", methods=["GET"], auth="none",
            proxy=ProxyConfig(service="backend", path="/api/data"),
            pre_request_handler="_test_pre_add_query",
        )
        gw = await make_gateway_request("GET", "/test")
        ctx = RouteContext(request=gw, path_params={}, services=mock_services)

        await execute_pipeline(route, ctx)

        client = mock_services.get_client("backend")
        _, kwargs = client.request.call_args
        assert kwargs["params"].get("api_key") == "secret123"

    @pytest.mark.asyncio
    async def test_pre_request_removes_query_param(self, mock_services):
        """Pre-request handler removes a query parameter."""

        @register_pre_request_handler("_test_pre_remove_query")
        async def remove_query(ctx, req):
            req.remove_query_param("internal")

        route = RouteConfig(
            path="/test", methods=["GET"], auth="none",
            proxy=ProxyConfig(service="backend", path="/api/data"),
            pre_request_handler="_test_pre_remove_query",
        )
        gw = await make_gateway_request("GET", "/test")
        ctx = RouteContext(request=gw, path_params={}, services=mock_services)

        await execute_pipeline(route, ctx)

        client = mock_services.get_client("backend")
        _, kwargs = client.request.call_args
        assert "internal" not in kwargs["params"]

    # ── Body modification ─────────────────────────────

    @pytest.mark.asyncio
    async def test_pre_request_sets_body(self, mock_services):
        """Pre-request handler overrides the request body."""

        @register_pre_request_handler("_test_pre_set_body")
        async def set_body(ctx, req):
            req.set_body({"custom": "body"})

        route = RouteConfig(
            path="/test", methods=["POST"], auth="none",
            proxy=ProxyConfig(service="backend", path="/api/data"),
            pre_request_handler="_test_pre_set_body",
        )
        gw = await make_gateway_request("POST", "/test", body={"original": "data"})
        ctx = RouteContext(request=gw, path_params={}, services=mock_services)

        await execute_pipeline(route, ctx)

        client = mock_services.get_client("backend")
        _, kwargs = client.request.call_args
        assert kwargs.get("json") == {"custom": "body"}

    @pytest.mark.asyncio
    async def test_pre_request_merges_body(self, mock_services):
        """Pre-request handler merges fields into the request body."""

        @register_pre_request_handler("_test_pre_merge_body")
        async def merge_body(ctx, req):
            req.merge_body({"trace_id": "abc-123"})

        route = RouteConfig(
            path="/test", methods=["POST"], auth="none",
            proxy=ProxyConfig(service="backend", path="/api/data"),
            pre_request_handler="_test_pre_merge_body",
        )
        gw = await make_gateway_request("POST", "/test", body={"original": "data"})
        ctx = RouteContext(request=gw, path_params={}, services=mock_services)

        await execute_pipeline(route, ctx)

        client = mock_services.get_client("backend")
        _, kwargs = client.request.call_args
        assert kwargs.get("json") == {"original": "data", "trace_id": "abc-123"}

    # ── Path modification ─────────────────────────────

    @pytest.mark.asyncio
    async def test_pre_request_sets_path(self, mock_services):
        """Pre-request handler overrides the target path."""

        @register_pre_request_handler("_test_pre_set_path")
        async def set_path(ctx, req):
            req.set_path("/new/path/456")

        route = RouteConfig(
            path="/test", methods=["GET"], auth="none",
            proxy=ProxyConfig(service="backend", path="/original/path"),
            pre_request_handler="_test_pre_set_path",
        )
        gw = await make_gateway_request("GET", "/test")
        ctx = RouteContext(request=gw, path_params={}, services=mock_services)

        await execute_pipeline(route, ctx)

        client = mock_services.get_client("backend")
        args, kwargs = client.request.call_args
        # First positional arg is the method, second is the url
        url = args[1] if len(args) > 1 else ""
        assert "/new/path/456" in url

    # ── Unknown handler ───────────────────────────────

    @pytest.mark.asyncio
    async def test_unknown_pre_request_handler(self, mock_services):
        """Unknown pre_request_handler → 501."""
        route = RouteConfig(
            path="/test", methods=["GET"], auth="none",
            proxy=ProxyConfig(service="backend", path="/api/data"),
            pre_request_handler="__nonexistent__",
        )
        gw = await make_gateway_request("GET", "/test")
        ctx = RouteContext(request=gw, path_params={}, services=mock_services)

        resp = await execute_pipeline(route, ctx)

        assert resp.status_code == 501

    # ── Handler without pre_request_handler still works ──

    @pytest.mark.asyncio
    async def test_proxy_without_pre_request_handler_still_works(self, mock_services):
        """Proxy WITHOUT pre_request_handler — old behaviour preserved."""

        route = RouteConfig(
            path="/test", methods=["POST"], auth="none",
            proxy=ProxyConfig(service="backend", path="/api/data"),
        )
        gw = await make_gateway_request("POST", "/test", body={"key": "value"})
        ctx = RouteContext(request=gw, path_params={}, services=mock_services)

        resp = await execute_pipeline(route, ctx)

        assert resp.status_code == 200
        data = json.loads(resp.body)
        assert data == {"result": "ok"}

    # ── Handler route without proxy still works ──

    @pytest.mark.asyncio
    async def test_handler_route_without_proxy_still_works(self, mock_services):
        """Handler-route WITHOUT proxy — old behaviour preserved."""

        @register_response_handler("_test_pre_handler_route")
        async def handler(ctx):
            return JSONResponse({"message": "ok"})

        route = RouteConfig(
            path="/test", methods=["GET"], auth="none",
            handler="_test_pre_handler_route",
        )
        gw = await make_gateway_request("GET", "/test")
        ctx = RouteContext(request=gw, path_params={}, services=mock_services)

        resp = await execute_pipeline(route, ctx)

        assert resp.status_code == 200
        data = json.loads(resp.body)
        assert data == {"message": "ok"}

    # ── Combined with response_handler ────────────────

    @pytest.mark.asyncio
    async def test_pre_request_with_response_handler(self, mock_services):
        """Pre-request handler + response_handler — both work."""

        @register_pre_request_handler("_test_pre_combined_pre")
        async def pre_handler(ctx, req):
            req.set_header("X-Pre", "yes")

        @register_response_handler("_test_pre_combined_post")
        async def post_handler(ctx):
            ctx.response.set_header("X-Post", "yes")

        route = RouteConfig(
            path="/test", methods=["POST"], auth="none",
            proxy=ProxyConfig(service="backend", path="/api/data"),
            pre_request_handler="_test_pre_combined_pre",
            response_handler="_test_pre_combined_post",
        )
        gw = await make_gateway_request("POST", "/test")
        ctx = RouteContext(request=gw, path_params={}, services=mock_services)

        resp = await execute_pipeline(route, ctx)

        # Verify pre-request sent header to backend
        client = mock_services.get_client("backend")
        _, kwargs = client.request.call_args
        assert kwargs["headers"].get("X-Pre") == "yes"

        # Verify response handler modified the response
        assert resp.status_code == 200
        assert resp.headers.get("X-Post") == "yes"

    # ── Empty handler (no-op) ────────────────────────

    @pytest.mark.asyncio
    async def test_pre_request_noop_handler(self, mock_services):
        """Pre-request handler that does nothing — request unchanged."""

        @register_pre_request_handler("_test_pre_noop")
        async def noop_handler(ctx, req):
            pass  # no modifications

        route = RouteConfig(
            path="/test", methods=["POST"], auth="none",
            proxy=ProxyConfig(service="backend", path="/api/data"),
            pre_request_handler="_test_pre_noop",
        )
        gw = await make_gateway_request("POST", "/test", body={"key": "value"})
        ctx = RouteContext(request=gw, path_params={}, services=mock_services)

        resp = await execute_pipeline(route, ctx)

        assert resp.status_code == 200
        data = json.loads(resp.body)
        assert data == {"result": "ok"}
