"""
Tests for ProxyResponseBuilder and proxy route response_handler pipeline.
"""

import json
from unittest.mock import MagicMock

import pytest
import requests
from fastapi.responses import JSONResponse
from starlette.requests import Request

from app.engine.context import RouteContext
from app.engine.models import ProxyConfig, ResponseConfig, RouteConfig
from app.engine.proxy_response import ProxyResponseBuilder
from app.engine.pipeline import execute_pipeline
from app.engine.registry import (
    register_response_handler,
    response_handler_registry,
    ServiceRegistry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_raw_response(status_code=200, body=None, headers=None, content_type="application/json"):
    """Create a mock requests.Response with given properties."""
    mock = MagicMock(spec=requests.Response)
    mock.status_code = status_code
    mock.ok = status_code < 400
    mock.headers = headers or {"Content-Type": content_type}
    if body is not None:
        body_bytes = json.dumps(body).encode() if isinstance(body, (dict, list)) else str(body).encode()
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
# ProxyResponseBuilder Tests
# ===================================================================

class TestProxyResponseBuilder:

    def test_body_property_parses_json(self):
        raw = make_raw_response(body={"key": "value"})
        builder = ProxyResponseBuilder(raw)
        assert builder.body == {"key": "value"}

    def test_body_property_non_json(self):
        raw = make_raw_response(body="plain text", content_type="text/plain")
        builder = ProxyResponseBuilder(raw)
        assert builder.body == b"plain text"

    def test_set_status(self):
        raw = make_raw_response(status_code=200)
        builder = ProxyResponseBuilder(raw)
        builder.set_status(201)
        result = builder.finalize()
        assert result.status_code == 201

    def test_set_header(self):
        raw = make_raw_response()
        builder = ProxyResponseBuilder(raw)
        builder.set_header("X-Custom", "value")
        result = builder.finalize()
        assert result.headers.get("X-Custom") == "value"

    def test_remove_header(self):
        raw = make_raw_response(headers={"X-Internal": "secret"})
        builder = ProxyResponseBuilder(raw)
        builder.remove_header("X-Internal")
        result = builder.finalize()
        assert "x-internal" not in result.headers

    def test_set_body(self):
        raw = make_raw_response(body={"original": "data"})
        builder = ProxyResponseBuilder(raw)
        builder.set_body({"new": "body"})
        result = builder.finalize()
        data = json.loads(result.body)
        assert data == {"new": "body"}

    def test_set_json_alias(self):
        raw = make_raw_response(body={"original": "data"})
        builder = ProxyResponseBuilder(raw)
        builder.set_json({"aliased": "body"})
        result = builder.finalize()
        data = json.loads(result.body)
        assert data == {"aliased": "body"}

    def test_merge_body_dict(self):
        raw = make_raw_response(body={"a": 1, "b": 2})
        builder = ProxyResponseBuilder(raw)
        builder.merge_body({"c": 3})
        result = builder.finalize()
        data = json.loads(result.body)
        assert data == {"a": 1, "b": 2, "c": 3}

    def test_merge_body_non_dict(self):
        raw = make_raw_response(body="string", content_type="text/plain")
        builder = ProxyResponseBuilder(raw)
        builder.merge_body({"a": 1})
        result = builder.finalize()
        data = json.loads(result.body)
        assert data == {"a": 1}

    def test_keep_fields(self):
        raw = make_raw_response(body={"a": 1, "b": 2, "c": 3})
        builder = ProxyResponseBuilder(raw)
        builder.keep_fields(["a", "c"])
        result = builder.finalize()
        data = json.loads(result.body)
        assert data == {"a": 1, "c": 3}

    def test_keep_fields_non_dict(self):
        raw = make_raw_response(body=[1, 2, 3])
        builder = ProxyResponseBuilder(raw)
        builder.keep_fields(["a"])
        result = builder.finalize()
        data = json.loads(result.body)
        assert data == [1, 2, 3]  # unchanged

    def test_remove_fields(self):
        raw = make_raw_response(body={"a": 1, "b": 2, "c": 3})
        builder = ProxyResponseBuilder(raw)
        builder.remove_fields(["b"])
        result = builder.finalize()
        data = json.loads(result.body)
        assert data == {"a": 1, "c": 3}

    def test_set_cookie(self):
        raw = make_raw_response()
        builder = ProxyResponseBuilder(raw)
        builder.set_cookie("session", "abc123", httponly=True, samesite="strict")
        result = builder.finalize()
        # Starlette set_cookie produces Set-Cookie headers
        cookie_headers = [v for k, v in result.headers.items() if k.lower() == "set-cookie"]
        assert len(cookie_headers) == 1
        assert "session=abc123" in cookie_headers[0]
        assert "HttpOnly" in cookie_headers[0]
        assert "samesite=strict" in cookie_headers[0].lower()

    def test_multiple_cookies(self):
        raw = make_raw_response()
        builder = ProxyResponseBuilder(raw)
        builder.set_cookie("a", "1")
        builder.set_cookie("b", "2")
        result = builder.finalize()
        cookie_headers = [v for k, v in result.headers.items() if k.lower() == "set-cookie"]
        assert len(cookie_headers) == 2

    def test_passthrough_ignores_modifications(self):
        raw = make_raw_response(status_code=200, body={"msg": "ok"})
        builder = ProxyResponseBuilder(raw)
        builder.set_status(500)
        builder.set_body({"bad": "data"})
        builder.passthrough()
        result = builder.finalize()
        data = json.loads(result.body)
        assert result.status_code == 200
        assert data == {"msg": "ok"}

    def test_finalize_preserves_status(self):
        raw = make_raw_response(status_code=404, body={"error": "not found"})
        builder = ProxyResponseBuilder(raw)
        result = builder.finalize()
        assert result.status_code == 404
        data = json.loads(result.body)
        assert data == {"error": "not found"}

    def test_finalize_non_json_response(self):
        raw = make_raw_response(body="binary data", content_type="application/octet-stream")
        builder = ProxyResponseBuilder(raw)
        result = builder.finalize()
        assert result.status_code == 200
        assert result.body == b"binary data"
        assert result.media_type == "application/octet-stream"

    def test_status_code_property(self):
        raw = make_raw_response(status_code=201)
        builder = ProxyResponseBuilder(raw)
        assert builder.status_code == 201
        builder.set_status(202)
        assert builder.status_code == 202


# ===================================================================
# Pipeline Integration Tests
# ===================================================================

class TestPipelineProxyResponseHandler:

    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        """Register test handlers and clean up after test."""
        # These will be registered by the test methods themselves
        # because we need unique names
        yield
        # Clean up registered handlers
        names_to_remove = []
        for name in list(response_handler_registry._items.keys()):
            if name.startswith("_test_proxy_resp_"):
                names_to_remove.append(name)
        for name in names_to_remove:
            del response_handler_registry._items[name]

    @pytest.fixture
    def mock_services(self):
        """Create a service registry with a mock backend."""
        reg = ServiceRegistry({"backend": {"base_url": "http://backend:8000"}})
        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.ok = True
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"access_token": "abc", "refresh_token": "xyz", "extra": "field"}
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_resp.content = b'{"access_token": "abc", "refresh_token": "xyz", "extra": "field"}'
        client = reg.get_client("backend")
        client.request = MagicMock(return_value=mock_resp)
        return reg

    @pytest.mark.asyncio
    async def test_proxy_with_response_handler_modifies_body(self, mock_services):
        """Proxy route + response_handler: handler modifies the proxy response."""

        @register_response_handler("_test_proxy_resp_modify_body")
        async def handler(ctx):
            ctx.response.keep_fields(["access_token"])
            ctx.response.set_header("X-Modified", "yes")

        route = RouteConfig(
            path="/test",
            methods=["POST"],
            auth="none",
            proxy=ProxyConfig(service="backend", path="/api/token"),
            response_handler="_test_proxy_resp_modify_body",
        )
        gw = await make_gateway_request("POST", "/test", body={"grant": "password"})
        ctx = RouteContext(request=gw, path_params={}, services=mock_services)

        resp = await execute_pipeline(route, ctx)

        assert resp.status_code == 200
        data = json.loads(resp.body)
        assert data == {"access_token": "abc"}
        assert resp.headers.get("X-Modified") == "yes"

    @pytest.mark.asyncio
    async def test_proxy_with_response_handler_set_cookie(self, mock_services):
        """Proxy route + response_handler: handler adds Set-Cookie."""

        @register_response_handler("_test_proxy_resp_cookie")
        async def handler(ctx):
            body = ctx.response.body
            ctx.response.set_cookie("refresh_token", body["refresh_token"], httponly=True, samesite="strict")
            ctx.response.remove_fields(["refresh_token"])

        route = RouteConfig(
            path="/test",
            methods=["POST"],
            auth="none",
            proxy=ProxyConfig(service="backend", path="/api/token"),
            response_handler="_test_proxy_resp_cookie",
        )
        gw = await make_gateway_request("POST", "/test", body={"grant": "password"})
        ctx = RouteContext(request=gw, path_params={}, services=mock_services)

        resp = await execute_pipeline(route, ctx)

        assert resp.status_code == 200
        data = json.loads(resp.body)
        assert "access_token" in data
        assert "refresh_token" not in data
        cookie_headers = [v for k, v in resp.headers.items() if k.lower() == "set-cookie"]
        assert len(cookie_headers) == 1
        assert "refresh_token=xyz" in cookie_headers[0]

    @pytest.mark.asyncio
    async def test_proxy_with_response_handler_passthrough(self, mock_services):
        """Proxy route + response_handler: handler returns None (passthrough)."""

        @register_response_handler("_test_proxy_resp_passthrough")
        async def handler(ctx):
            ctx.response.passthrough()

        route = RouteConfig(
            path="/test",
            methods=["POST"],
            auth="none",
            proxy=ProxyConfig(service="backend", path="/api/token"),
            response_handler="_test_proxy_resp_passthrough",
        )
        gw = await make_gateway_request("POST", "/test")
        ctx = RouteContext(request=gw, path_params={}, services=mock_services)

        resp = await execute_pipeline(route, ctx)

        assert resp.status_code == 200
        data = json.loads(resp.body)
        assert data == {"access_token": "abc", "refresh_token": "xyz", "extra": "field"}

    @pytest.mark.asyncio
    async def test_proxy_with_unknown_response_handler(self, mock_services):
        """Proxy route + unknown response_handler -> 501."""

        route = RouteConfig(
            path="/test",
            methods=["POST"],
            auth="none",
            proxy=ProxyConfig(service="backend", path="/api/token"),
            response_handler="__nonexistent_handler__",
        )
        gw = await make_gateway_request("POST", "/test")
        ctx = RouteContext(request=gw, path_params={}, services=mock_services)

        resp = await execute_pipeline(route, ctx)

        assert resp.status_code == 501

    @pytest.mark.asyncio
    async def test_proxy_with_response_handler_and_wrap(self, mock_services):
        """Proxy route + response_handler + response.wrap — wrap applies after handler."""

        @register_response_handler("_test_proxy_resp_wrap")
        async def handler(ctx):
            ctx.response.keep_fields(["access_token"])

        route = RouteConfig(
            path="/test",
            methods=["POST"],
            auth="none",
            proxy=ProxyConfig(service="backend", path="/api/token"),
            response_handler="_test_proxy_resp_wrap",
            response=ResponseConfig(wrap="data"),
        )
        gw = await make_gateway_request("POST", "/test")
        ctx = RouteContext(request=gw, path_params={}, services=mock_services)

        resp = await execute_pipeline(route, ctx)

        assert resp.status_code == 200
        data = json.loads(resp.body)
        assert data == {"data": {"access_token": "abc"}}

    @pytest.mark.asyncio
    async def test_proxy_without_response_handler_still_works(self, mock_services):
        """Proxy route WITHOUT response_handler — old behaviour preserved."""

        route = RouteConfig(
            path="/test",
            methods=["POST"],
            auth="none",
            proxy=ProxyConfig(service="backend", path="/api/token"),
        )
        gw = await make_gateway_request("POST", "/test")
        ctx = RouteContext(request=gw, path_params={}, services=mock_services)

        resp = await execute_pipeline(route, ctx)

        assert resp.status_code == 200
        data = json.loads(resp.body)
        assert data == {"access_token": "abc", "refresh_token": "xyz", "extra": "field"}

    @pytest.mark.asyncio
    async def test_handler_route_without_proxy_still_works(self, mock_services):
        """Handler-based route WITHOUT proxy — old behaviour preserved."""

        @register_response_handler("_test_proxy_resp_regular_handler")
        async def handler(ctx):
            return JSONResponse({"message": "ok"})

        route = RouteConfig(
            path="/test",
            methods=["GET"],
            auth="none",
            handler="_test_proxy_resp_regular_handler",
        )
        gw = await make_gateway_request("GET", "/test")
        ctx = RouteContext(request=gw, path_params={}, services=mock_services)

        resp = await execute_pipeline(route, ctx)

        assert resp.status_code == 200
        data = json.loads(resp.body)
        assert data == {"message": "ok"}
