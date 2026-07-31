"""
Tests for ResponseBuilder and proxy route response_handler pipeline.

ResponseBuilder lives through the entire pipeline — any handler can
accumulate modifications via ctx.response modification methods.
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
from app.engine.proxy_response import ResponseBuilder
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
# ResponseBuilder Unit Tests
# ===================================================================

class TestResponseBuilder:

    def test_create_empty(self):
        """Builder can be created without arguments."""
        builder = ResponseBuilder()
        assert builder.is_empty() is True
        assert builder.has_base() is False
        assert builder.status_code is None

    def test_set_base(self):
        """set_base stores the raw response and sets status_code."""
        raw = make_raw_response(status_code=200, body={"msg": "ok"})
        builder = ResponseBuilder()
        builder.set_base(raw)
        assert builder.has_base() is True
        assert builder.status_code == 200
        assert builder.body == {"msg": "ok"}

    def test_body_raises_without_base(self):
        """Accessing .body without base raises RuntimeError."""
        builder = ResponseBuilder()
        with pytest.raises(RuntimeError):
            _ = builder.body

    def test_status_code_property_without_base(self):
        """status_code returns None when neither base nor set_status."""
        builder = ResponseBuilder()
        assert builder.status_code is None

    def test_set_status(self):
        """set_status overrides the status code."""
        builder = ResponseBuilder()
        builder.set_status(201)
        assert builder.status_code == 201
        assert builder.is_empty() is False

    def test_set_status_overrides_base(self):
        """set_status overrides base status."""
        raw = make_raw_response(status_code=200)
        builder = ResponseBuilder()
        builder.set_base(raw)
        builder.set_status(201)
        assert builder.status_code == 201

    def test_set_header(self):
        """set_header adds a response header."""
        builder = ResponseBuilder()
        builder.set_header("X-Custom", "value")
        resp = builder.apply_to(JSONResponse({}))
        assert resp.headers.get("X-Custom") == "value"

    def test_remove_header(self):
        """remove_header removes a header from the response."""
        builder = ResponseBuilder()
        builder.remove_header("Content-Type")
        resp = JSONResponse({"a": 1})  # has Content-Type
        resp = builder.apply_to(resp)
        assert "content-type" not in resp.headers

    def test_set_body(self):
        """set_body replaces the response body."""
        builder = ResponseBuilder()
        builder.set_body({"new": "body"})
        assert builder.is_empty() is False
        resp = builder.apply_to(JSONResponse({"original": "data"}))
        data = json.loads(resp.body)
        assert data == {"new": "body"}

    def test_merge_body_with_base(self):
        """merge_body adds fields when base is available."""
        raw = make_raw_response(body={"a": 1, "b": 2})
        builder = ResponseBuilder()
        builder.set_base(raw)
        builder.merge_body({"c": 3})
        resp = builder.finalize()
        data = json.loads(resp.body)
        assert data == {"a": 1, "b": 2, "c": 3}

    def test_merge_body_accumulates(self):
        """Multiple merge_body calls accumulate."""
        raw = make_raw_response(body={"a": 1})
        builder = ResponseBuilder()
        builder.set_base(raw)
        builder.merge_body({"b": 2})
        builder.merge_body({"c": 3})
        resp = builder.finalize()
        data = json.loads(resp.body)
        assert data == {"a": 1, "b": 2, "c": 3}

    def test_keep_fields(self):
        """keep_fields filters to only specified fields."""
        raw = make_raw_response(body={"a": 1, "b": 2, "c": 3})
        builder = ResponseBuilder()
        builder.set_base(raw)
        builder.keep_fields(["a", "c"])
        resp = builder.finalize()
        data = json.loads(resp.body)
        assert data == {"a": 1, "c": 3}

    def test_remove_fields(self):
        """remove_fields removes specified fields."""
        raw = make_raw_response(body={"a": 1, "b": 2, "c": 3})
        builder = ResponseBuilder()
        builder.set_base(raw)
        builder.remove_fields(["b"])
        resp = builder.finalize()
        data = json.loads(resp.body)
        assert data == {"a": 1, "c": 3}

    def test_keep_and_remove_mutually_exclusive(self):
        """Last call between keep_fields and remove_fields wins."""
        raw = make_raw_response(body={"a": 1, "b": 2, "c": 3})
        builder = ResponseBuilder()
        builder.set_base(raw)
        builder.keep_fields(["a"])
        builder.remove_fields(["a"])  # overrides keep
        resp = builder.finalize()
        data = json.loads(resp.body)
        # keep_fields sets _keep=["a"], _remove=None
        # remove_fields overrides: _remove=["a"], _keep=None
        # So "a" gets removed, result is {"b": 2, "c": 3}
        assert data == {"b": 2, "c": 3}

    def test_set_cookie(self):
        """set_cookie adds a Set-Cookie header."""
        builder = ResponseBuilder()
        builder.set_cookie("session", "abc123", httponly=True, samesite="strict")
        resp = builder.apply_to(JSONResponse({}))
        cookie_headers = [v for k, v in resp.headers.items() if k.lower() == "set-cookie"]
        assert len(cookie_headers) == 1
        assert "session=abc123" in cookie_headers[0]
        assert "HttpOnly" in cookie_headers[0]
        assert "samesite" in cookie_headers[0].lower()

    def test_multiple_cookies(self):
        """Multiple set_cookie calls produce multiple Set-Cookie headers."""
        builder = ResponseBuilder()
        builder.set_cookie("a", "1")
        builder.set_cookie("b", "2")
        resp = builder.apply_to(JSONResponse({}))
        cookie_headers = [v for k, v in resp.headers.items() if k.lower() == "set-cookie"]
        assert len(cookie_headers) == 2

    def test_passthrough(self):
        """passthrough applies no modifications."""
        raw = make_raw_response(body={"msg": "ok"})
        builder = ResponseBuilder()
        builder.set_base(raw)
        builder.set_status(500)
        builder.set_body({"bad": "data"})
        builder.passthrough()
        assert builder.is_empty() is False  # passthrough is a modification
        resp = builder.finalize()
        data = json.loads(resp.body)
        assert resp.status_code == 200
        assert data == {"msg": "ok"}

    def test_finalize_preserves_status(self):
        """finalize preserves the base response status."""
        raw = make_raw_response(status_code=404, body={"error": "not found"})
        builder = ResponseBuilder()
        builder.set_base(raw)
        resp = builder.finalize()
        assert resp.status_code == 404
        data = json.loads(resp.body)
        assert data == {"error": "not found"}

    def test_finalize_non_json_response(self):
        """finalize works with non-JSON responses."""
        raw = make_raw_response(body=b"binary data", content_type="application/octet-stream")
        builder = ResponseBuilder()
        builder.set_base(raw)
        resp = builder.finalize()
        assert resp.status_code == 200
        assert resp.body == b"binary data"

    def test_finalize_requires_base(self):
        """finalize without base raises RuntimeError."""
        builder = ResponseBuilder()
        with pytest.raises(RuntimeError):
            builder.finalize()

    def test_apply_to_empty_builder(self):
        """apply_to with empty builder returns unchanged response."""
        builder = ResponseBuilder()
        original = JSONResponse({"msg": "ok"})
        result = builder.apply_to(original)
        assert result is original  # same object

    def test_apply_to_passthrough(self):
        """apply_to with passthrough returns unchanged response."""
        builder = ResponseBuilder()
        builder.passthrough()
        original = JSONResponse({"msg": "ok"})
        result = builder.apply_to(original)
        assert result is original

    def test_is_empty_initial(self):
        """Fresh builder is empty."""
        assert ResponseBuilder().is_empty() is True

    def test_is_empty_after_set_status(self):
        """Builder with modifications is not empty."""
        builder = ResponseBuilder()
        builder.set_status(201)
        assert builder.is_empty() is False

    def test_is_empty_after_set_header(self):
        builder = ResponseBuilder()
        builder.set_header("X", "v")
        assert builder.is_empty() is False

    def test_is_empty_after_remove_header(self):
        builder = ResponseBuilder()
        builder.remove_header("X")
        assert builder.is_empty() is False

    def test_is_empty_after_set_cookie(self):
        builder = ResponseBuilder()
        builder.set_cookie("k", "v")
        assert builder.is_empty() is False

    def test_is_empty_after_body_override(self):
        builder = ResponseBuilder()
        builder.set_body({"x": 1})
        assert builder.is_empty() is False

    def test_is_empty_after_merge_body(self):
        builder = ResponseBuilder()
        builder.merge_body({"x": 1})
        assert builder.is_empty() is False

    def test_is_empty_after_keep_fields(self):
        builder = ResponseBuilder()
        builder.keep_fields(["x"])
        assert builder.is_empty() is False

    def test_is_empty_after_remove_fields(self):
        builder = ResponseBuilder()
        builder.remove_fields(["x"])
        assert builder.is_empty() is False

    def test_is_empty_after_passthrough(self):
        builder = ResponseBuilder()
        builder.passthrough()
        assert builder.is_empty() is False


# ===================================================================
# Pipeline Integration Tests
# ===================================================================

class TestPipelineResponseBuilder:

    @pytest.fixture(autouse=True)
    def setup_teardown(self):
        """Register test handlers and clean up after test."""
        yield
        names_to_remove = []
        for name in list(response_handler_registry._items.keys()):
            if name.startswith("_test_resp_builder_"):
                names_to_remove.append(name)
        for name in names_to_remove:
            del response_handler_registry._items[name]

    @pytest.fixture
    def mock_services(self):
        """Create a service registry with a mock backend."""
        reg = ServiceRegistry({"backend": {"base_url": "http://backend:8000"}})
        mock_resp = MagicMock(spec=httpx.Response)
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"access_token": "abc", "refresh_token": "xyz", "extra": "field"}
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_resp.content = b'{"access_token": "abc", "refresh_token": "xyz", "extra": "field"}'
        client = reg.get_client("backend")
        client.request = AsyncMock(return_value=mock_resp)
        return reg

    # ── Proxy + response_handler ─────────────────────

    @pytest.mark.asyncio
    async def test_proxy_with_response_handler_keep_fields(self, mock_services):
        """Proxy + response_handler: handler filters fields."""

        @register_response_handler("_test_resp_builder_keep")
        async def handler(ctx):
            ctx.response.keep_fields(["access_token"])
            ctx.response.set_header("X-Modified", "yes")

        route = RouteConfig(
            path="/test", methods=["POST"], auth="none",
            proxy=ProxyConfig(service="backend", path="/api/token"),
            response_handler="_test_resp_builder_keep",
        )
        gw = await make_gateway_request("POST", "/test")
        ctx = RouteContext(request=gw, path_params={}, services=mock_services)

        resp = await execute_pipeline(route, ctx)

        assert resp.status_code == 200
        data = json.loads(resp.body)
        assert data == {"access_token": "abc"}
        assert resp.headers.get("X-Modified") == "yes"

    @pytest.mark.asyncio
    async def test_proxy_with_response_handler_set_cookie(self, mock_services):
        """Proxy + response_handler: handler adds Set-Cookie."""

        @register_response_handler("_test_resp_builder_cookie")
        async def handler(ctx):
            body = ctx.response.body
            ctx.response.set_cookie("refresh_token", body["refresh_token"], httponly=True, samesite="strict")
            ctx.response.remove_fields(["refresh_token"])

        route = RouteConfig(
            path="/test", methods=["POST"], auth="none",
            proxy=ProxyConfig(service="backend", path="/api/token"),
            response_handler="_test_resp_builder_cookie",
        )
        gw = await make_gateway_request("POST", "/test")
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
        """Proxy + response_handler: passthrough returns unchanged response."""

        @register_response_handler("_test_resp_builder_passthrough")
        async def handler(ctx):
            ctx.response.passthrough()

        route = RouteConfig(
            path="/test", methods=["POST"], auth="none",
            proxy=ProxyConfig(service="backend", path="/api/token"),
            response_handler="_test_resp_builder_passthrough",
        )
        gw = await make_gateway_request("POST", "/test")
        ctx = RouteContext(request=gw, path_params={}, services=mock_services)

        resp = await execute_pipeline(route, ctx)

        assert resp.status_code == 200
        data = json.loads(resp.body)
        assert data == {"access_token": "abc", "refresh_token": "xyz", "extra": "field"}

    @pytest.mark.asyncio
    async def test_proxy_with_unknown_response_handler(self, mock_services):
        """Proxy + unknown response_handler → 501."""

        route = RouteConfig(
            path="/test", methods=["POST"], auth="none",
            proxy=ProxyConfig(service="backend", path="/api/token"),
            response_handler="__nonexistent_handler__",
        )
        gw = await make_gateway_request("POST", "/test")
        ctx = RouteContext(request=gw, path_params={}, services=mock_services)

        resp = await execute_pipeline(route, ctx)

        assert resp.status_code == 501

    @pytest.mark.asyncio
    async def test_proxy_with_response_handler_and_wrap(self, mock_services):
        """Proxy + response_handler + response.wrap — wrap applies after handler."""

        @register_response_handler("_test_resp_builder_wrap")
        async def handler(ctx):
            ctx.response.keep_fields(["access_token"])

        route = RouteConfig(
            path="/test", methods=["POST"], auth="none",
            proxy=ProxyConfig(service="backend", path="/api/token"),
            response_handler="_test_resp_builder_wrap",
            response=ResponseConfig(wrap="data"),
        )
        gw = await make_gateway_request("POST", "/test")
        ctx = RouteContext(request=gw, path_params={}, services=mock_services)

        resp = await execute_pipeline(route, ctx)

        assert resp.status_code == 200
        data = json.loads(resp.body)
        assert data == {"data": {"access_token": "abc"}}

    # ── Proxy without response_handler ───────────────

    @pytest.mark.asyncio
    async def test_proxy_without_response_handler_still_works(self, mock_services):
        """Proxy WITHOUT response_handler — old behaviour preserved."""

        route = RouteConfig(
            path="/test", methods=["POST"], auth="none",
            proxy=ProxyConfig(service="backend", path="/api/token"),
        )
        gw = await make_gateway_request("POST", "/test")
        ctx = RouteContext(request=gw, path_params={}, services=mock_services)

        resp = await execute_pipeline(route, ctx)

        assert resp.status_code == 200
        data = json.loads(resp.body)
        assert data == {"access_token": "abc", "refresh_token": "xyz", "extra": "field"}

    # ── Handler route (no proxy) ─────────────────────

    @pytest.mark.asyncio
    async def test_handler_route_without_proxy_still_works(self, mock_services):
        """Handler-route WITHOUT proxy — old behaviour preserved."""

        @register_response_handler("_test_resp_builder_handler")
        async def handler(ctx):
            return JSONResponse({"message": "ok"})

        route = RouteConfig(
            path="/test", methods=["GET"], auth="none",
            handler="_test_resp_builder_handler",
        )
        gw = await make_gateway_request("GET", "/test")
        ctx = RouteContext(request=gw, path_params={}, services=mock_services)

        resp = await execute_pipeline(route, ctx)

        assert resp.status_code == 200
        data = json.loads(resp.body)
        assert data == {"message": "ok"}

    # ── ctx.response accessible in access handlers ───

    @pytest.mark.asyncio
    async def test_access_handler_can_set_header(self, mock_services):
        """Access handler can set header via ctx.response."""

        from app.engine.registry import register_access_handler

        @register_access_handler("_test_resp_builder_set_header_from_access")
        def access_handler(ctx):
            ctx.response.set_header("X-From-Access", "yes")
            return ctx.allow()

        @register_response_handler("_test_resp_builder_return_ok")
        async def handler(ctx):
            return JSONResponse({"msg": "ok"})

        route = RouteConfig(
            path="/test", methods=["GET"], auth="none",
            access="_test_resp_builder_set_header_from_access",
            handler="_test_resp_builder_return_ok",
        )
        gw = await make_gateway_request("GET", "/test")
        ctx = RouteContext(request=gw, path_params={}, services=mock_services)

        resp = await execute_pipeline(route, ctx)

        assert resp.status_code == 200
        assert resp.headers.get("X-From-Access") == "yes"

    @pytest.mark.asyncio
    async def test_access_handler_can_set_cookie(self, mock_services):
        """Access handler can set cookie via ctx.response."""

        from app.engine.registry import register_access_handler

        @register_access_handler("_test_resp_builder_cookie_from_access")
        def access_handler(ctx):
            ctx.response.set_cookie("session", "abc", httponly=True)
            return ctx.allow()

        @register_response_handler("_test_resp_builder_cookie_handler")
        async def handler(ctx):
            return JSONResponse({"msg": "ok"})

        route = RouteConfig(
            path="/test", methods=["GET"], auth="none",
            access="_test_resp_builder_cookie_from_access",
            handler="_test_resp_builder_cookie_handler",
        )
        gw = await make_gateway_request("GET", "/test")
        ctx = RouteContext(request=gw, path_params={}, services=mock_services)

        resp = await execute_pipeline(route, ctx)

        assert resp.status_code == 200
        cookie_headers = [v for k, v in resp.headers.items() if k.lower() == "set-cookie"]
        assert len(cookie_headers) == 1
        assert "session=abc" in cookie_headers[0]

    @pytest.mark.asyncio
    async def test_builder_works_for_proxy_without_handler(self, mock_services):
        """Builder modifications apply to plain proxy routes too."""

        from app.engine.registry import register_access_handler

        @register_access_handler("_test_resp_builder_proxy_header")
        def access_handler(ctx):
            ctx.response.set_header("X-Proxied", "true")
            return ctx.allow()

        route = RouteConfig(
            path="/test", methods=["GET"], auth="none",
            proxy=ProxyConfig(service="backend", path="/api/data"),
            access="_test_resp_builder_proxy_header",
        )
        gw = await make_gateway_request("GET", "/test")
        ctx = RouteContext(request=gw, path_params={}, services=mock_services)

        resp = await execute_pipeline(route, ctx)

        assert resp.status_code == 200
        assert resp.headers.get("X-Proxied") == "true"
