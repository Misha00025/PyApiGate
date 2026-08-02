"""
Body integrity tests — real HTTP roundtrip through the proxy pipeline.

Spins up a minimal TCP HTTP server that checks Content-Length matches
the actual body. Uses _execute_proxy_raw to test the full header
forwarding logic in _build_headers.
"""

import asyncio
import json

import pytest
import pytest_asyncio
import httpx
from starlette.requests import Request

from app.engine.context import GatewayRequest, RouteContext
from app.engine.models import ProxyConfig, RouteConfig
from app.engine.proxy import _execute_proxy_raw
from app.engine.registry import ServiceRegistry


class ContentLengthChecker:
    """
    Minimal HTTP/1.1 server that reads exactly Content-Length bytes.
    Returns 400 if the body is shorter than declared Content-Length.
    """

    def __init__(self):
        self._server = None
        self._port = None

    @property
    def port(self) -> int:
        assert self._port is not None
        return self._port

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    async def start(self):
        self._server = await asyncio.start_server(
            self._handle, host="127.0.0.1", port=0
        )
        self._port = self._server.sockets[0].getsockname()[1]

    async def stop(self):
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            request_line = await reader.readline()
            parts = request_line.decode().strip().split()
            if len(parts) < 2:
                await writer.drain()
                writer.close()
                return

            headers = {}
            while True:
                line = await reader.readline()
                decoded = line.decode().strip()
                if not decoded:
                    break
                if ":" in decoded:
                    key, value = decoded.split(":", 1)
                    headers[key.strip().lower()] = value.strip()

            content_length = int(headers.get("content-length", 0))
            body_bytes = b""
            if content_length > 0:
                body_bytes = await reader.readexactly(content_length)

            response_body = json.dumps({"received": len(body_bytes)})
            response = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: application/json\r\n"
                f"Content-Length: {len(response_body)}\r\n"
                "\r\n"
                + response_body
            )
            writer.write(response.encode())
            await writer.drain()
        except asyncio.IncompleteReadError:
            response = (
                "HTTP/1.1 400 Bad Request\r\n"
                "Content-Type: text/plain\r\n"
                "Content-Length: 40\r\n"
                "\r\n"
                "Content-Length declared larger than actual body"
            )
            writer.write(response.encode())
            await writer.drain()
        except httpx.RemoteProtocolError:
            response = (
                "HTTP/1.1 400 Bad Request\r\n"
                "Content-Type: text/plain\r\n"
                "Content-Length: 38\r\n"
                "\r\n"
                "HTTP protocol error (Content-Length leak)"
            )
            writer.write(response.encode())
            await writer.drain()
        finally:
            try:
                writer.close()
            except Exception:
                pass


@pytest_asyncio.fixture
async def backend():
    server = ContentLengthChecker()
    await server.start()
    yield server
    await server.stop()


class TestProxyBodyIntegrity:

    async def _execute_proxy(
        self,
        backend,
        method: str = "POST",
        body: dict | None = None,
        content_type: str = "application/json",
    ):
        """Helper: build context and execute proxy request."""
        body_bytes = json.dumps(body).encode() if body is not None else b""
        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": method,
            "path": "/proxy/test",
            "headers": [
                (b"content-type", content_type.encode()),
                (b"content-length", str(len(body_bytes)).encode()),
                (b"x-forwarded-for", b"127.0.0.1"),
            ],
            "query_string": b"",
            "client": ("127.0.0.1", 50000),
            "server": ("127.0.0.1", 8080),
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

        reg = ServiceRegistry({
            "backend": {"base_url": backend.url, "timeout": 10},
        })

        route = RouteConfig(
            path="/proxy/test",
            methods=[method],
            proxy=ProxyConfig(service="backend", path="/api/data"),
        )

        ctx = RouteContext(
            request=gw,
            path_params={},
            services=reg,
        )

        return await _execute_proxy_raw(route, ctx)

    @pytest.mark.asyncio
    async def test_json_post_body_integrity(self, backend):
        """
        Simple JSON POST through proxy — Content-Length must match body.
        This is the control test: no header manipulation, should pass.
        """
        resp = await self._execute_proxy(
            backend,
            method="POST",
            body={"key": "value"},
        )
        assert resp.status_code == 200, (
            f"Body integrity broken! Status: {resp.status_code}. "
            "This means even a basic proxy POST fails."
        )

    @pytest.mark.asyncio
    async def test_get_no_body(self, backend):
        """
        GET request through proxy — no Content-Length should be sent.
        """
        resp = await self._execute_proxy(
            backend,
            method="GET",
            body=None,
        )
        assert resp.status_code == 200, (
            f"GET request failed! Status: {resp.status_code}. "
            "GET requests should work fine."
        )

    @pytest.mark.asyncio
    async def test_large_body_post(self, backend):
        """
        POST with larger body through proxy — Content-Length must match.
        """
        large_body = {"data": "x" * 10000}
        resp = await self._execute_proxy(
            backend,
            method="POST",
            body=large_body,
        )
        assert resp.status_code == 200, (
            f"Large body POST failed! Status: {resp.status_code}. "
            "Content-Length mismatch on larger payloads."
        )
