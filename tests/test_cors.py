"""
Tests for CORS configuration in app.json.
"""

import os

import pytest
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app import create_app

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))


class TestCorsConfig:
    def test_cors_not_configured(self, monkeypatch):
        """When cors is absent, no CORSMiddleware is added."""
        monkeypatch.setenv("APP_CONFIG", "tests/test_app.json")
        app = create_app()
        middlewares = [m.cls for m in app.user_middleware]
        assert CORSMiddleware not in middlewares

    def test_cors_disabled_explicitly(self, tmp_path, monkeypatch):
        """When cors is null, no CORSMiddleware is added."""
        routes_yaml = tmp_path / "routes.yaml"
        routes_yaml.write_text("base_path: ''\nservices: {}\nroutes: []\n")
        config_file = tmp_path / "app.json"
        config_file.write_text(
            '{"logging": {"level": "INFO"}, "routes": {"files": ["routes.yaml"]},'
            ' "cors": null, "request_id": {"header": "X-Request-ID"}}'
        )
        monkeypatch.setenv("APP_CONFIG", str(config_file))
        app = create_app()
        middlewares = [m.cls for m in app.user_middleware]
        assert CORSMiddleware not in middlewares

    def test_cors_enabled(self, tmp_path, monkeypatch):
        """When cors is an object, CORSMiddleware is added with given params."""
        routes_yaml = tmp_path / "routes.yaml"
        routes_yaml.write_text("base_path: ''\nservices: {}\nroutes: []\n")
        config_file = tmp_path / "app.json"
        config_file.write_text('''{
            "logging": {"level": "INFO"},
            "routes": {"files": ["routes.yaml"]},
            "cors": {
                "allow_origins": ["https://example.com"],
                "allow_methods": ["GET", "POST"],
                "allow_headers": ["Content-Type"],
                "allow_credentials": true
            },
            "request_id": {"header": "X-Request-ID"}
        }''')
        monkeypatch.setenv("APP_CONFIG", str(config_file))
        app = create_app()
        middlewares = [m.cls for m in app.user_middleware]
        assert CORSMiddleware in middlewares

    def test_cors_defaults(self, tmp_path, monkeypatch):
        """When cors has no fields, defaults are used."""
        routes_yaml = tmp_path / "routes.yaml"
        routes_yaml.write_text("base_path: ''\nservices: {}\nroutes: []\n")
        config_file = tmp_path / "app.json"
        config_file.write_text(
            '{"logging": {"level": "INFO"}, "routes": {"files": ["routes.yaml"]},'
            ' "cors": {}, "request_id": {"header": "X-Request-ID"}}'
        )
        monkeypatch.setenv("APP_CONFIG", str(config_file))
        app = create_app()
        middlewares = [m.cls for m in app.user_middleware]
        assert CORSMiddleware in middlewares
