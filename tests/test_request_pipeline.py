"""
Tests for GatewayRequest body/json caching and Pipeline execution.

Uses Starlette Request directly (no real HTTP server) so tests run
fast and require no external services.
"""

import json

import pytest
from starlette.requests import Request

from app.engine.context import GatewayRequest, RouteContext
from app.engine.models import RouteConfig, ResponseConfig
from app.engine.pipeline import execute_pipeline
from app.engine.registry import register_access_handler, register_response_handler
from app.engine.status import ok


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

async def _make_request(method="GET", path="/test", body=None,
                        content_type="application/json"):
    if isinstance(body, dict):
        body_bytes = json.dumps(body).encode()
    elif isinstance(body, str):
        body_bytes = body.encode()
    elif isinstance(body, bytes):
        body_bytes = body
    else:
        body_bytes = b""

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

    return Request(scope, receive=receive)


async def _make_gw(method="GET", path="/test", body=None,
                   content_type="application/json"):
    req = await _make_request(method, path, body, content_type)
    return GatewayRequest(req)


# ---------------------------------------------------------------------------
# GatewayRequest
# ---------------------------------------------------------------------------

class TestGatewayRequest:
    @pytest.mark.asyncio
    async def test_load_body_caches_json(self):
        gw = await _make_gw(body={"key": "value"}, content_type="application/json")
        assert gw.body is None
        assert gw.json is None

        await gw.load_body()

        assert gw.body == b'{"key": "value"}'
        assert gw.json == {"key": "value"}

    @pytest.mark.asyncio
    async def test_load_body_idempotent(self):
        gw = await _make_gw(body={"x": 1})
        await gw.load_body()
        body1 = gw.body

        await gw.load_body()  # second call

        assert gw.body == body1

    @pytest.mark.asyncio
    async def test_load_body_text_plain(self):
        gw = await _make_gw(body="hello", content_type="text/plain")
        await gw.load_body()
        assert gw.body == b"hello"
        assert gw.json is None

    @pytest.mark.asyncio
    async def test_load_body_no_content_type(self):
        gw = await _make_gw(body="{}", content_type="")
        await gw.load_body()
        assert gw.body is not None
        assert gw.json is None

    @pytest.mark.asyncio
    async def test_is_json_true(self):
        gw = await _make_gw(body={"key": "value"}, content_type="application/json")
        assert gw.is_json is True

    @pytest.mark.asyncio
    async def test_is_json_false_for_multipart(self):
        gw = await _make_gw(body="data", content_type="multipart/form-data")
        assert gw.is_json is False

    @pytest.mark.asyncio
    async def test_is_json_false_for_octet(self):
        gw = await _make_gw(body=b"data", content_type="application/octet-stream")
        assert gw.is_json is False

    @pytest.mark.asyncio
    async def test_content_type_property(self):
        gw = await _make_gw(body="{}", content_type="application/json; charset=utf-8")
        assert "json" in gw.content_type


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class TestPipeline:
    @pytest.mark.asyncio
    async def test_pipeline_auth_none_handler(self):
        @register_response_handler("_test_pipeline_ok_handler")
        async def handler(ctx):
            return ok({"message": "ok"})

        route = RouteConfig(path="/test", handler="_test_pipeline_ok_handler",
                            auth="none")
        gw = await _make_gw("GET", "/test")
        ctx = RouteContext(request=gw, path_params={})

        resp = await execute_pipeline(route, ctx, auth_strategy=None)

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_pipeline_auth_required_success(self):
        @register_response_handler("_test_pipeline_auth_ok")
        async def handler(ctx):
            return ok({"message": "ok"})

        route = RouteConfig(path="/test", handler="_test_pipeline_auth_ok",
                            auth="required")
        gw = await _make_gw("GET", "/test")
        ctx = RouteContext(request=gw, path_params={})

        def auth_strategy(ctx):
            return {"sub": "user123"}

        resp = await execute_pipeline(route, ctx, auth_strategy=auth_strategy)

        assert resp.status_code == 200
        assert ctx.jwt == {"sub": "user123"}

    @pytest.mark.asyncio
    async def test_pipeline_auth_required_no_strategy(self):
        route = RouteConfig(path="/test", auth="required")
        gw = await _make_gw("GET", "/test")
        ctx = RouteContext(request=gw, path_params={})

        resp = await execute_pipeline(route, ctx, auth_strategy=None)

        assert resp.status_code == 501

    @pytest.mark.asyncio
    async def test_pipeline_auth_failure(self):
        @register_response_handler("_test_pipeline_auth_fail_handler")
        async def handler(ctx):
            return ok({"message": "ok"})

        route = RouteConfig(path="/test", handler="_test_pipeline_auth_fail_handler",
                            auth="required")
        gw = await _make_gw("GET", "/test")
        ctx = RouteContext(request=gw, path_params={})

        def auth_strategy(ctx):
            return None

        resp = await execute_pipeline(route, ctx, auth_strategy=auth_strategy)

        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_pipeline_unknown_access_handler(self):
        route = RouteConfig(path="/test", auth="none",
                            access="nonexistent_handler")
        gw = await _make_gw("GET", "/test")
        ctx = RouteContext(request=gw, path_params={})

        resp = await execute_pipeline(route, ctx)

        assert resp.status_code == 501

    @pytest.mark.asyncio
    async def test_pipeline_access_denied_returns_403_with_header(self):
        @register_access_handler("_test_deny")
        def deny_handler(ctx):
            return ctx.deny()

        @register_response_handler("_test_pipeline_deny_handler")
        async def handler(ctx):
            return ok({"message": "ok"})

        route = RouteConfig(path="/test", handler="_test_pipeline_deny_handler",
                            auth="none", access="_test_deny")
        gw = await _make_gw("GET", "/test")
        ctx = RouteContext(request=gw, path_params={})

        resp = await execute_pipeline(route, ctx)

        assert resp.status_code == 403
        assert resp.headers.get("X-Deny-Reason") == "_test_deny"

    @pytest.mark.asyncio
    async def test_pipeline_response_wrap(self):
        @register_response_handler("_test_wrap_handler")
        async def handler(ctx):
            return ok({"items": [1, 2]})

        route = RouteConfig(path="/test", handler="_test_wrap_handler",
                            auth="none",
                            response=ResponseConfig(wrap="data"))
        gw = await _make_gw("GET", "/test")
        ctx = RouteContext(request=gw, path_params={})

        resp = await execute_pipeline(route, ctx)

        assert resp.status_code == 200
        data = json.loads(resp.body)
        assert data == {"data": {"items": [1, 2]}}
