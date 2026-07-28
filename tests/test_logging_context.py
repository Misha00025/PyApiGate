"""
Tests for logging context and source expression resolution in log format.
"""

import logging
import pytest
from starlette.requests import Request

from app.engine.context import GatewayRequest, RouteContext
from app.logging_context import set_logging_context, clear_logging_context, resolve_source
from app.logging_formatter import SourceExpressionFormatter


@pytest.fixture
def log_record():
    return logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=42,
        msg="test message",
        args=(),
        exc_info=None,
    )


class TestResolveSource:
    def test_resolve_jwt_field(self, ctx_with_jwt):
        """resolve_source returns the JWT field value."""
        set_logging_context(ctx_with_jwt)
        try:
            result = resolve_source("{jwt.userId}")
            assert result == "user123"
        finally:
            clear_logging_context()

    def test_resolve_jwt_field_none(self, ctx_with_jwt):
        set_logging_context(ctx_with_jwt)
        try:
            result = resolve_source("{jwt.nonexistent}")
            assert result == "-"
        finally:
            clear_logging_context()

    def test_resolve_jwt_without_context(self):
        result = resolve_source("{jwt.userId}")
        assert result == "-"

    def test_resolve_path_field(self, ctx_with_path_params):
        set_logging_context(ctx_with_path_params)
        try:
            result = resolve_source("{path.user_id}")
            assert result == "42"
        finally:
            clear_logging_context()

    def test_resolve_query_field(self, ctx_with_query):
        set_logging_context(ctx_with_query)
        try:
            result = resolve_source("{query.token}")
            assert result == "abc123"
        finally:
            clear_logging_context()

    def test_literal_passed_through(self):
        result = resolve_source("literal_string")
        assert result == "literal_string"

    def test_invalid_expression_passed_through(self):
        result = resolve_source("{invalid}")
        assert result == "{invalid}"


class TestSourceExpressionFormatter:
    def test_formatter_resolves_jwt(self, ctx_with_jwt, log_record):
        set_logging_context(ctx_with_jwt)
        try:
            fmt = SourceExpressionFormatter(
                "[userId={jwt.userId}] %(message)s"
            )
            result = fmt.format(log_record)
            assert result == "[userId=user123] test message"
        finally:
            clear_logging_context()

    def test_formatter_handles_missing_context(self, log_record):
        fmt = SourceExpressionFormatter(
            "[userId={jwt.userId}] %(message)s"
        )
        result = fmt.format(log_record)
        assert result == "[userId=-] test message"

    def test_formatter_without_expressions(self, log_record):
        fmt = SourceExpressionFormatter(
            "%(asctime)s [%(levelname)s] %(message)s"
        )
        result = fmt.format(log_record)
        assert "[userId=" not in result
        assert "test message" in result


# Fixtures
@pytest.fixture
def ctx_with_jwt():
    """Create a RouteContext with JWT payload containing userId."""
    gw = _make_gw()
    return RouteContext(
        request=gw,
        path_params={},
        jwt={"userId": "user123", "sub": "user123", "email": "user@example.com"},
    )


@pytest.fixture
def ctx_with_path_params():
    gw = _make_gw()
    return RouteContext(
        request=gw,
        path_params={"user_id": "42"},
        jwt=None,
    )


@pytest.fixture
def ctx_with_query():
    gw = _make_gw(query_string=b"token=abc123")
    return RouteContext(
        request=gw,
        path_params={},
        jwt=None,
    )


def _make_gw(method="GET", path="/test", query_string=b""):
    """Helper to create a GatewayRequest."""
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

    import asyncio
    req = Request(scope, receive=receive)
    return GatewayRequest(req)
