"""
Tests that pipeline logging respects source expressions in log format.
"""

import logging
import json
import pytest
from starlette.requests import Request

from app.engine.context import GatewayRequest, RouteContext
from app.engine.models import RouteConfig
from app.engine.pipeline import execute_pipeline
from app.engine.status import ok
from app.engine.registry import register_response_handler
from app.logging_config import setup_logging


@pytest.mark.asyncio
async def test_pipeline_log_contains_user_id(capsys):
    """Pipeline log line contains resolved {jwt.userId}."""
    setup_logging({
        "logging": {
            "level": "INFO",
            "format": "%(message)s [userId={jwt.userId}]"
        }
    })

    @register_response_handler("_test_log_userid")
    async def handler(ctx):
        return ok({"msg": "ok"})

    route = RouteConfig(path="/test", handler="_test_log_userid", auth="required")
    gw = await _make_gw("GET", "/test")
    ctx = RouteContext(request=gw, path_params={})

    def auth_strategy(ctx):
        return {"userId": "user123"}

    await execute_pipeline(route, ctx, auth_strategy=auth_strategy)
    captured = capsys.readouterr()
    assert "[userId=user123]" in captured.out, f"Expected userId=user123 in stdout, got: {captured.out}"


@pytest.mark.asyncio
async def test_pipeline_log_user_id_anonymous(capsys):
    """Pipeline log shows '-' for userId when auth=none."""
    setup_logging({
        "logging": {
            "level": "INFO",
            "format": "%(message)s [userId={jwt.userId}]"
        }
    })

    @register_response_handler("_test_log_anon")
    async def handler(ctx):
        return ok({"msg": "ok"})

    route = RouteConfig(path="/test", handler="_test_log_anon", auth="none")
    gw = await _make_gw("GET", "/test")
    ctx = RouteContext(request=gw, path_params={})

    await execute_pipeline(route, ctx, auth_strategy=None)
    captured = capsys.readouterr()
    assert "[userId=-]" in captured.out, f"Expected [userId=-] in stdout, got: {captured.out}"


async def _make_gw(method="GET", path="/test", query_string=b""):
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "path": path,
        "headers": [],
        "query_string": query_string,
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
        return {"type": "http.request", "body": b"", "more_body": False}

    req = Request(scope, receive=receive)
    return GatewayRequest(req)
