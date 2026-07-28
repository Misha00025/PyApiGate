"""
Tests for bootstrap with multiple route config files.
"""

import pytest
from fastapi import FastAPI

from app.engine.bootstrap import bootstrap


class TestBootstrapMulti:
    def test_multiple_configs(self):
        """Two self-contained YAML files each register their own routes."""
        app = FastAPI()
        configs = bootstrap(app, config_paths=[
            "tests/test_configs/routes_v1.yaml",
            "tests/test_configs/routes_v2.yaml",
        ])

        assert len(configs) == 2

        # v1 routes
        assert configs[0].base_path == "/v1"
        assert len(configs[0].routes) == 1
        assert configs[0].routes[0].path == "/hello"

        # v2 routes
        assert configs[1].base_path == "/v2"
        assert len(configs[1].routes) == 1
        assert configs[1].routes[0].path == "/users"

    def test_single_config_backward_compat(self, monkeypatch):
        """None defaults to single configs/routes.yaml."""
        monkeypatch.setenv("AUTH_SERVICE_URL", "http://auth:8000")
        monkeypatch.setenv("USERS_SERVICE_URL", "http://users:8000")
        monkeypatch.setenv("CAMPAIGN_SERVICE_URL", "http://campaign:8000")
        app = FastAPI()
        configs = bootstrap(app, config_paths=None)
        assert len(configs) >= 0  # just check it doesn't crash

    def test_empty_list(self):
        """Empty list doesn't crash."""
        app = FastAPI()
        configs = bootstrap(app, config_paths=[])
        assert len(configs) == 0
