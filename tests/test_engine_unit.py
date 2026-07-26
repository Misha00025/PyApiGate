"""
Unit-тесты для PyApiGate engine.
Не требуют поднятия Flask или Docker.
"""

import pytest
from flask import Flask
from app.engine.models import (
    AuthConfig, RouteConfig, ProxyConfig, ParamsConfig,
    GatewayConfig, ServiceConfig, RouteType
)
from app.engine.context import RouteContext, AccessResult
from app.engine.registry import (
    ServiceRegistry, ServiceClient,
    access_handler_registry, response_handler_registry,
    register_access_handler, register_response_handler,
)
from app.engine.status import ok, forbidden, unauthorized


@pytest.fixture
def app_ctx():
    app = Flask(__name__)
    with app.app_context():
        yield


class TestModels:
    def test_route_type_proxy(self):
        route = RouteConfig(path="/test", proxy=ProxyConfig(service="srv", path="/test"))
        assert route.route_type == RouteType.PROXY

    def test_route_type_handler(self):
        route = RouteConfig(path="/test", handler="my_handler")
        assert route.route_type == RouteType.HANDLER

    def test_get_access_handler_string(self):
        route = RouteConfig(path="/test", access="group_member")
        assert route.get_access_handler("GET") == "group_member"
        assert route.get_access_handler("POST") == "group_member"

    def test_get_access_handler_dict(self):
        route = RouteConfig(path="/test", access={"GET": "reader", "POST": "writer"})
        assert route.get_access_handler("GET") == "reader"
        assert route.get_access_handler("POST") == "writer"
        assert route.get_access_handler("DELETE") is None

    def test_get_access_handler_none(self):
        route = RouteConfig(path="/test")
        assert route.get_access_handler("GET") is None


class TestContext:
    def test_allow(self):
        ctx = RouteContext(request=None, path_params={})
        result = ctx.allow()
        assert result.allowed is True
        assert result.response is None

    def test_deny_custom(self):
        ctx = RouteContext(request=None, path_params={})
        custom = ("custom", 418)
        result = ctx.deny(custom)
        assert result.allowed is False
        assert result.response == ("custom", 418)


class TestRegistry:
    def test_service_registry(self):
        reg = ServiceRegistry({"srv1": {"base_url": "http://localhost:8000"}})
        client = reg.srv1
        assert isinstance(client, ServiceClient)
        assert client.base_url == "http://localhost:8000"

    def test_service_registry_unknown(self):
        reg = ServiceRegistry({})
        with pytest.raises(KeyError):
            reg.unknown_service

    def test_access_handler_registry(self):
        key = "ut_test_handler"

        @register_access_handler(key)
        def handler(ctx):
            return ctx.allow()

        assert access_handler_registry.has(key)
        assert access_handler_registry.get(key) is handler

    def test_response_handler_registry(self):
        key = "ut_test_response"

        @register_response_handler(key)
        def handler(ctx):
            return ok({"result": "ok"})

        assert response_handler_registry.get(key) is handler


class TestStatus:
    def test_ok(self, app_ctx):
        resp, code = ok({"data": "test"})
        assert code == 200

    def test_forbidden(self, app_ctx):
        resp, code = forbidden()
        assert code == 403

    def test_unauthorized(self, app_ctx):
        resp, code = unauthorized()
        assert code == 401


class TestAuthConfig:
    def test_default_auth_config(self):
        config = GatewayConfig()
        assert config.auth.strategy == "none"
        assert config.auth.public_key_path is None
        assert config.auth.expected_issuer is None

    def test_auth_registry_rsa_jwt_registered(self):
        import app.auth_strategies  # noqa: F401 — triggers @register_auth_strategy
        from app.engine.registry import auth_strategy_registry
        assert auth_strategy_registry.has("rsa_jwt")

    def test_auth_registry_unknown(self):
        from app.engine.registry import auth_strategy_registry
        assert not auth_strategy_registry.has("nonexistent")
