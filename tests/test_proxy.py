"""
Tests for Proxy and Param Injection in PyApiGate.

Tests _resolve_path, _resolve_source, _build_query_params, _build_body,
_build_headers, _to_response, and execute_proxy.
"""

import json as _json
from unittest.mock import MagicMock

import pytest
import requests
from starlette.requests import Request

from app.engine.context import GatewayRequest, RouteContext
from app.engine.models import ParamsConfig, ProxyConfig, RouteConfig
from app.engine.proxy import (
    _build_body,
    _build_headers,
    _build_query_params,
    _resolve_path,
    _resolve_source,
    _to_response,
    execute_proxy,
)
from app.engine.registry import ServiceRegistry


async def make_gateway_request(
    method="GET",
    path="/test",
    body=None,
    query=None,
    content_type="application/json",
):
    body_bytes = _json.dumps(body).encode() if body is not None else b""
    query_str = (
        "&".join(f"{k}={v}" for k, v in query.items()).encode()
        if query
        else b""
    )
    headers = [
        (b"content-type", content_type.encode()),
        (b"content-length", str(len(body_bytes)).encode()),
    ]
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "path": path,
        "headers": headers,
        "query_string": query_str,
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def ctx_with_jwt():
    """
    Returns a RouteContext with JWT, path_params, and a minimal request
    suitable for _resolve_source tests.
    """
    gw = None
    # Set up a mock request with query_params for {query.*} tests
    mock_req = MagicMock()
    mock_req.query_params = {"filter": "active"}
    return RouteContext(
        request=mock_req,
        path_params={"group_id": "42", "user_id": "99"},
        jwt={"userId": "user_123", "sub": "user_123"},
    )


@pytest.fixture
def mock_services():
    reg = ServiceRegistry({"test_svc": {"base_url": "http://localhost:8000"}})
    mock_resp = MagicMock(spec=requests.Response)
    mock_resp.ok = True
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"result": "ok"}
    mock_resp.headers = {"Content-Type": "application/json"}
    mock_resp.content = b'{"result": "ok"}'
    client = reg.get_client("test_svc")
    client.request = MagicMock(return_value=mock_resp)
    return reg


@pytest.fixture
def route_with_proxy():
    return RouteConfig(
        path="/test",
        auth="none",
        proxy=ProxyConfig(service="test_svc", path="/api/data"),
    )


@pytest.fixture
def ctx_with_services(mock_services):
    gw = MagicMock()
    gw.method = "GET"
    gw.headers = {}
    gw.query_params = {}
    gw.json = None
    return RouteContext(
        request=gw,
        path_params={},
        jwt={"sub": "user123"},
        services=mock_services,
    )


# ---------------------------------------------------------------------------
# _resolve_path
# ---------------------------------------------------------------------------


class TestResolvePath:
    def test_basic_substitution(self):
        result = _resolve_path("/api/users/{user_id}", {"user_id": "42"})
        assert result == "/api/users/42"

    def test_multiple_params(self):
        result = _resolve_path(
            "/groups/{gid}/items/{iid}", {"gid": "1", "iid": "99"}
        )
        assert result == "/groups/1/items/99"

    def test_no_placeholders(self):
        result = _resolve_path("/api/hello", {})
        assert result == "/api/hello"

    def test_partial_substitution(self):
        result = _resolve_path(
            "/api/users/{user_id}/posts", {"user_id": "42"}
        )
        assert result == "/api/users/42/posts"


# ---------------------------------------------------------------------------
# _resolve_source
# ---------------------------------------------------------------------------


class TestResolveSource:
    def test_jwt_field(self):
        ctx = ctx_with_jwt()
        result = _resolve_source("{jwt.userId}", ctx)
        assert result == "user_123"

    def test_path_field(self):
        ctx = ctx_with_jwt()
        result = _resolve_source("{path.group_id}", ctx)
        assert result == "42"

    def test_query_field(self):
        ctx = ctx_with_jwt()
        result = _resolve_source("{query.filter}", ctx)
        assert result == "active"

    def test_literal_string(self):
        ctx = ctx_with_jwt()
        result = _resolve_source("plain_string", ctx)
        assert result == "plain_string"

    def test_jwt_missing_field(self):
        ctx = ctx_with_jwt()
        result = _resolve_source("{jwt.nonexistent}", ctx)
        assert result is None

    def test_jwt_userId_fallbacks_to_sub(self):
        ctx = RouteContext(
            request=None, path_params={}, jwt={"sub": "fallback_user"}
        )
        result = _resolve_source("{jwt.userId}", ctx)
        assert result == "fallback_user"

    def test_none_jwt_returns_none(self):
        ctx = RouteContext(request=None, path_params={}, jwt=None)
        result = _resolve_source("{jwt.sub}", ctx)
        assert result is None


# ---------------------------------------------------------------------------
# _build_query_params
# ---------------------------------------------------------------------------


class TestBuildQueryParams:
    @pytest.mark.asyncio
    async def test_no_params_config(self):
        route = RouteConfig(path="/test", auth="none")
        ctx = RouteContext(
            request=await make_gateway_request(query={"a": "1"}),
            path_params={},
            jwt=None,
        )
        result = _build_query_params(route, ctx)
        assert result == {"a": "1"}

    @pytest.mark.asyncio
    async def test_wildcard_with_jwt(self):
        route = RouteConfig(
            path="/test", auth="none", params=ParamsConfig(query="*")
        )
        ctx = RouteContext(
            request=await make_gateway_request(query={"a": "1"}),
            path_params={},
            jwt={"sub": "user123"},
        )
        result = _build_query_params(route, ctx)
        assert result == {"a": "1", "userId": "user123"}

    @pytest.mark.asyncio
    async def test_dict_mapping(self):
        route = RouteConfig(
            path="/test",
            auth="none",
            params=ParamsConfig(query={"dest": "{jwt.sub}"}),
        )
        ctx = RouteContext(
            request=await make_gateway_request(),
            path_params={},
            jwt={"sub": "user123"},
        )
        result = _build_query_params(route, ctx)
        assert result == {"dest": "user123"}

    @pytest.mark.asyncio
    async def test_dict_mapping_with_star(self):
        route = RouteConfig(
            path="/test",
            auth="none",
            params=ParamsConfig(query={"userId": "{jwt.sub}", "*": "*"}),
        )
        ctx = RouteContext(
            request=await make_gateway_request(query={"a": "1"}),
            path_params={},
            jwt={"sub": "user123"},
        )
        result = _build_query_params(route, ctx)
        assert result == {"userId": "user123", "a": "1"}

    @pytest.mark.asyncio
    async def test_wildcard_no_jwt_skips_userId(self):
        route = RouteConfig(
            path="/test", auth="none", params=ParamsConfig(query="*")
        )
        ctx = RouteContext(
            request=await make_gateway_request(query={"a": "1"}),
            path_params={},
            jwt=None,
        )
        result = _build_query_params(route, ctx)
        assert result == {"a": "1"}
        assert "userId" not in result

    @pytest.mark.asyncio
    async def test_dict_mapping_override_existing(self):
        route = RouteConfig(
            path="/test",
            auth="none",
            params=ParamsConfig(query={"override": "{jwt.sub}"}),
        )
        ctx = RouteContext(
            request=await make_gateway_request(query={"override": "old"}),
            path_params={},
            jwt={"sub": "new_value"},
        )
        result = _build_query_params(route, ctx)
        assert result == {"override": "new_value"}


# ---------------------------------------------------------------------------
# _build_body
# ---------------------------------------------------------------------------


class TestBuildBody:
    @pytest.mark.asyncio
    async def test_no_body_config(self):
        route = RouteConfig(path="/test", auth="none")
        ctx = RouteContext(
            request=await make_gateway_request(body={"key": "val"}),
            path_params={},
            jwt=None,
        )
        result = await _build_body(route, ctx)
        assert result == {"key": "val"}

    @pytest.mark.asyncio
    async def test_body_injection_from_jwt(self):
        route = RouteConfig(
            path="/test",
            auth="none",
            params=ParamsConfig(body={"userId": "{jwt.sub}"}),
        )
        ctx = RouteContext(
            request=await make_gateway_request(body={"key": "val"}),
            path_params={},
            jwt={"sub": "user123"},
        )
        result = await _build_body(route, ctx)
        assert result == {"key": "val", "userId": "user123"}

    @pytest.mark.asyncio
    async def test_body_injection_from_path(self):
        route = RouteConfig(
            path="/test",
            auth="none",
            params=ParamsConfig(body={"groupId": "{path.group_id}"}),
        )
        ctx = RouteContext(
            request=await make_gateway_request(body={"key": "val"}),
            path_params={"group_id": "42"},
            jwt=None,
        )
        result = await _build_body(route, ctx)
        assert result == {"key": "val", "groupId": "42"}

    @pytest.mark.asyncio
    async def test_body_injection_empty_body(self):
        route = RouteConfig(
            path="/test",
            auth="none",
            params=ParamsConfig(body={"userId": "{jwt.sub}"}),
        )
        ctx = RouteContext(
            request=await make_gateway_request(body=None),
            path_params={},
            jwt={"sub": "user123"},
        )
        result = await _build_body(route, ctx)
        assert result == {"userId": "user123"}

    @pytest.mark.asyncio
    async def test_body_injection_no_body_config_no_json(self):
        route = RouteConfig(path="/test", auth="none", params=None)
        ctx = RouteContext(
            request=await make_gateway_request(body=None),
            path_params={},
            jwt=None,
        )
        result = await _build_body(route, ctx)
        assert result is None


# ---------------------------------------------------------------------------
# _build_headers
# ---------------------------------------------------------------------------


class TestBuildHeaders:
    @pytest.mark.asyncio
    async def test_filters_system_headers(self):
        gw = await make_gateway_request()
        ctx = RouteContext(request=gw, path_params={})
        proxy_cfg = ProxyConfig(service="test", path="/api", headers={})
        result = _build_headers(ctx, proxy_cfg)
        assert "content-type" not in result
        assert "host" not in result
        assert "content-length" not in result

    @pytest.mark.asyncio
    async def test_extra_headers_from_config(self):
        gw = await make_gateway_request()
        ctx = RouteContext(request=gw, path_params={})
        proxy_cfg = ProxyConfig(
            service="test",
            path="/api",
            headers={"X-Custom": "value", "Authorization": "Bearer token"},
        )
        result = _build_headers(ctx, proxy_cfg)
        assert result.get("X-Custom") == "value"
        assert result.get("Authorization") == "Bearer token"

    @pytest.mark.asyncio
    async def test_extra_headers_override_forwarded(self):
        gw = await make_gateway_request()
        ctx = RouteContext(request=gw, path_params={})
        proxy_cfg = ProxyConfig(
            service="test",
            path="/api",
            headers={"content-type": "application/xml"},
        )
        result = _build_headers(ctx, proxy_cfg)
        assert result.get("content-type") == "application/xml"


# ---------------------------------------------------------------------------
# _to_response
# ---------------------------------------------------------------------------


class TestToResponse:
    def test_json_response(self):
        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_resp.json.return_value = {"result": "ok"}
        result = _to_response(mock_resp)
        assert result.status_code == 200
        body = _json.loads(result.body)
        assert body == {"result": "ok"}

    def test_non_json_response(self):
        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.status_code = 200
        mock_resp.headers = {"Content-Type": "text/plain"}
        mock_resp.json.side_effect = ValueError("not json")
        mock_resp.content = b"hello world"
        result = _to_response(mock_resp)
        assert result.status_code == 200
        assert result.body == b"hello world"

    def test_error_status_preserved(self):
        mock_resp = MagicMock(spec=requests.Response)
        mock_resp.status_code = 404
        mock_resp.headers = {"Content-Type": "application/json"}
        mock_resp.json.return_value = {"error": "not found"}
        result = _to_response(mock_resp)
        assert result.status_code == 404
        body = _json.loads(result.body)
        assert body == {"error": "not found"}


# ---------------------------------------------------------------------------
# execute_proxy
# ---------------------------------------------------------------------------


class TestExecuteProxy:
    @pytest.mark.asyncio
    async def test_successful_proxy(self, route_with_proxy, ctx_with_services):
        resp = await execute_proxy(route_with_proxy, ctx_with_services)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_unknown_service(self):
        gw = await make_gateway_request()
        reg = ServiceRegistry({"known": {"base_url": "http://x"}})
        route = RouteConfig(
            path="/test",
            auth="none",
            proxy=ProxyConfig(service="unknown", path="/test"),
        )
        ctx = RouteContext(request=gw, path_params={}, services=reg)
        resp = await execute_proxy(route, ctx)
        assert resp.status_code == 501

    @pytest.mark.asyncio
    async def test_no_proxy_config(self):
        gw = await make_gateway_request()
        route = RouteConfig(path="/test", auth="none")
        ctx = RouteContext(request=gw, path_params={})
        resp = await execute_proxy(route, ctx)
        assert resp.status_code == 501

    @pytest.mark.asyncio
    async def test_proxy_with_path_params(self, mock_services):
        gw = await make_gateway_request(method="GET", path="/users/42")
        route = RouteConfig(
            path="/users/{user_id}",
            auth="none",
            proxy=ProxyConfig(service="test_svc", path="/api/users/{user_id}"),
        )
        ctx = RouteContext(
            request=gw,
            path_params={"user_id": "42"},
            jwt=None,
            services=mock_services,
        )
        resp = await execute_proxy(route, ctx)
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_post_with_body(self, mock_services):
        gw = await make_gateway_request(
            method="POST", path="/test", body={"key": "val"}
        )
        route = RouteConfig(
            path="/test",
            auth="none",
            proxy=ProxyConfig(service="test_svc", path="/api/data"),
        )
        ctx = RouteContext(
            request=gw,
            path_params={},
            jwt={"sub": "user123"},
            services=mock_services,
        )
        resp = await execute_proxy(route, ctx)
        assert resp.status_code == 200
