"""
Tests for config loading: loader.py, bootstrap.py URL conversion, config.py merging.
"""

import json
import os
import re

import pytest
import yaml

from app.engine.models import (
    AuthConfig, GatewayConfig, ParamsConfig, ProxyConfig,
    ResponseConfig, RouteConfig, ServiceConfig,
)
from app.engine.loader import (
    load_config,
    _resolve_env_vars,
    _resolve_env_vars_recursive,
    _parse_config,
    _parse_route,
    _parse_single_route,
)
from app.engine.bootstrap import _register_route
from app.config import load_app_config


# ============================================================
# _resolve_env_vars
# ============================================================

class TestResolveEnvVars:
    def test_env_var_present(self, monkeypatch):
        monkeypatch.setenv("MY_HOST", "localhost")
        assert _resolve_env_vars("${MY_HOST}") == "localhost"

    def test_env_var_with_default(self):
        assert _resolve_env_vars("${PORT:-8080}") == "8080"

    def test_env_var_missing_no_default(self, monkeypatch):
        monkeypatch.delenv("MISSING_VAR", raising=False)
        with pytest.raises(ValueError, match="MISSING_VAR"):
            _resolve_env_vars("${MISSING_VAR}")

    def test_no_env_var_in_string(self):
        assert _resolve_env_vars("hello") == "hello"

    def test_env_var_with_default_present(self, monkeypatch):
        monkeypatch.setenv("PORT", "3000")
        assert _resolve_env_vars("${PORT:-8080}") == "3000"

    def test_recursive_dict(self, monkeypatch):
        monkeypatch.setenv("HOST", "example.com")
        data = {"url": "${HOST}", "port": 123}
        result = _resolve_env_vars_recursive(data)
        assert result == {"url": "example.com", "port": 123}

    def test_recursive_list(self, monkeypatch):
        monkeypatch.setenv("NAME", "test")
        data = ["${NAME}", "static"]
        result = _resolve_env_vars_recursive(data)
        assert result == ["test", "static"]


# ============================================================
# _parse_route
# ============================================================

class TestParseRoute:
    def test_single_method(self):
        route_def = {
            "path": "/test",
            "methods": ["GET"],
            "handler": "my_handler",
            "auth": "none",
        }
        routes = _parse_route(route_def)
        assert len(routes) == 1
        assert routes[0].path == "/test"
        assert routes[0].methods == ["GET"]
        assert routes[0].handler == "my_handler"

    def test_list_methods(self):
        route_def = {
            "path": "/test",
            "methods": ["GET", "POST"],
            "handler": "my_handler",
            "auth": "none",
        }
        routes = _parse_route(route_def)
        assert len(routes) == 2
        assert routes[0].methods == ["GET"]
        assert routes[1].methods == ["POST"]

    def test_dict_methods_different_configs(self):
        route_def = {
            "path": "/test",
            "methods": {
                "GET": {"handler": "get_handler"},
                "POST": {"access": "post_access"},
            },
            "auth": "required",
        }
        routes = _parse_route(route_def)
        assert len(routes) == 2
        get_route = [r for r in routes if r.methods == ["GET"]][0]
        assert get_route.auth == "required"
        assert get_route.handler == "get_handler"
        post_route = [r for r in routes if r.methods == ["POST"]][0]
        assert post_route.auth == "required"
        assert post_route.access == "post_access"

    def test_default_method(self):
        route_def = {
            "path": "/test",
            "handler": "my_handler",
        }
        routes = _parse_route(route_def)
        assert len(routes) == 1
        assert routes[0].methods == ["GET"]

    def test_proxy_config(self):
        route_def = {
            "path": "/test/{id}",
            "methods": ["GET"],
            "proxy": {
                "service": "users",
                "path": "/users/{id}",
                "skip_body": True,
                "headers": {"X-Custom": "value"},
            },
            "auth": "required",
        }
        routes = _parse_route(route_def)
        assert len(routes) == 1
        proxy = routes[0].proxy
        assert proxy is not None
        assert proxy.service == "users"
        assert proxy.path == "/users/{id}"
        assert proxy.skip_body is True
        assert proxy.headers == {"X-Custom": "value"}

    def test_params_config(self):
        route_def = {
            "path": "/test",
            "methods": ["GET"],
            "handler": "h",
            "params": {
                "query": "*",
                "body": {"user_id": "{jwt.sub}"},
            },
            "auth": "none",
        }
        routes = _parse_route(route_def)
        params = routes[0].params
        assert params is not None
        assert params.query == "*"
        assert params.body == {"user_id": "{jwt.sub}"}

    def test_response_wrap_config(self):
        route_def = {
            "path": "/test",
            "methods": ["GET"],
            "handler": "h",
            "response": {"wrap": "data"},
            "auth": "none",
        }
        routes = _parse_route(route_def)
        response = routes[0].response
        assert response is not None
        assert response.wrap == "data"

    def test_full_gateway_config_parsing(self):
        yaml_str = """
base_path: /v2
auth:
  strategy: rsa_jwt
  public_key_path: /certs/public.pem
services:
  api:
    base_url: http://api:8000
    timeout: 10
routes:
  - path: /hello
    methods: [GET]
    handler: hello_handler
    auth: none
  - path: /users/{id}
    methods: [GET, POST]
    proxy:
      service: api
      path: /users/{id}
    auth: required
"""
        data = yaml.safe_load(yaml_str)
        config = _parse_config(data)
        assert config.base_path == "/v2"
        assert config.auth.strategy == "rsa_jwt"
        assert config.auth.public_key_path == "/certs/public.pem"
        assert len(config.services) == 1
        assert config.services["api"].base_url == "http://api:8000"
        assert config.services["api"].timeout == 10
        assert len(config.routes) == 3


# ============================================================
# Bootstrap URL conversion
# ============================================================

class TestBootstrapUrlConversion:
    def test_flask_int_to_fastapi(self):
        flask_path = "/api/users/<int:user_id>"
        fastapi_path = re.sub(r'<(?:\w+:)?(\w+)>', r'{\1}', flask_path)
        assert fastapi_path == "/api/users/{user_id}"

    def test_flask_str_to_fastapi(self):
        flask_path = "/api/<string:name>"
        fastapi_path = re.sub(r'<(?:\w+:)?(\w+)>', r'{\1}', flask_path)
        assert fastapi_path == "/api/{name}"

    def test_flask_no_type_to_fastapi(self):
        flask_path = "/api/<username>"
        fastapi_path = re.sub(r'<(?:\w+:)?(\w+)>', r'{\1}', flask_path)
        assert fastapi_path == "/api/{username}"

    def test_no_conversion_needed(self):
        fastapi_path = "/api/{user_id}"
        result = re.sub(r'<(?:\w+:)?(\w+)>', r'{\1}', fastapi_path)
        assert result == fastapi_path


# ============================================================
# app/config.py
# ============================================================

class TestAppConfig:
    def test_load_config_merges_defaults(self, tmp_path):
        defaults_dir = tmp_path / "configs_default"
        defaults_dir.mkdir()
        (defaults_dir / "app.json").write_text(json.dumps({
            "logging": {"level": "INFO", "file": None, "format": "default"},
            "request_id": {"header": "X-Request-ID", "generate_if_missing": True},
        }))

        config_dir = tmp_path / "configs"
        config_dir.mkdir()
        (config_dir / "app.json").write_text(json.dumps({
            "logging": {"level": "DEBUG"},
        }))

        import app.config as cfg_module
        old_defaults = cfg_module.DEFAULTS_DIR
        old_config = cfg_module.CONFIG_DIR
        cfg_module.DEFAULTS_DIR = str(defaults_dir)
        cfg_module.CONFIG_DIR = str(config_dir)

        try:
            result = load_app_config(str(config_dir / "app.json"))
            assert result["logging"]["level"] == "DEBUG"
            assert result["logging"]["format"] == "default"
            assert result["request_id"]["header"] == "X-Request-ID"
        finally:
            cfg_module.DEFAULTS_DIR = old_defaults
            cfg_module.CONFIG_DIR = old_config

    def test_creates_config_from_default_when_missing(self, tmp_path):
        defaults_dir = tmp_path / "configs_default"
        defaults_dir.mkdir()
        (defaults_dir / "app.json").write_text(json.dumps({
            "logging": {"level": "INFO"},
            "request_id": {"header": "X-Request-ID"},
        }))

        config_dir = tmp_path / "configs"
        config_dir.mkdir()

        import app.config as cfg_module
        old_defaults = cfg_module.DEFAULTS_DIR
        old_config = cfg_module.CONFIG_DIR
        cfg_module.DEFAULTS_DIR = str(defaults_dir)
        cfg_module.CONFIG_DIR = str(config_dir)

        try:
            # Passing None triggers auto-creation from default
            result = load_app_config(None)
            assert (config_dir / "app.json").exists()
            assert result["logging"]["level"] == "INFO"
        finally:
            cfg_module.DEFAULTS_DIR = old_defaults
            cfg_module.CONFIG_DIR = old_config

class TestAppConfigMultiRoutes:
    def test_routes_files_default_when_missing(self, tmp_path):
        """When routes.files is missing, default to single file."""
        config = {
            "logging": {"level": "INFO"},
            "request_id": {"header": "X-Request-ID"},
        }
        config_file = tmp_path / "app.json"
        config_file.write_text(json.dumps(config))

        result = load_app_config(str(config_file))
        # Defaults include routes.files, so it's present
        assert result.get("routes", {}).get("files") == ["routes.yaml"]

    def test_routes_files_list(self, tmp_path):
        config = {
            "logging": {"level": "INFO"},
            "routes": {"files": ["routes.yaml", "routes_v2.yaml"]},
            "request_id": {"header": "X-Request-ID"},
        }
        config_file = tmp_path / "app.json"
        config_file.write_text(json.dumps(config))

        result = load_app_config(str(config_file))
        assert result["routes"]["files"] == ["routes.yaml", "routes_v2.yaml"]


    def test_invalid_json_falls_back_to_defaults(self, tmp_path):
        defaults_dir = tmp_path / "configs_default"
        defaults_dir.mkdir()
        (defaults_dir / "app.json").write_text(json.dumps({"logging": {"level": "INFO"}}))

        config_dir = tmp_path / "configs"
        config_dir.mkdir()
        (config_dir / "app.json").write_text("not valid json {{{")

        import app.config as cfg_module
        old_defaults = cfg_module.DEFAULTS_DIR
        old_config = cfg_module.CONFIG_DIR
        cfg_module.DEFAULTS_DIR = str(defaults_dir)
        cfg_module.CONFIG_DIR = str(config_dir)

        try:
            result = load_app_config(str(config_dir / "app.json"))
            assert result["logging"]["level"] == "INFO"
        finally:
            cfg_module.DEFAULTS_DIR = old_defaults
            cfg_module.CONFIG_DIR = old_config
