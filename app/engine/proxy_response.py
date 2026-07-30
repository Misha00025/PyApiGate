"""
ProxyResponseBuilder — controlled wrapper around backend HTTP response.

Provides a limited, intentional API for response handlers to modify
the backend response. The handler cannot access the raw requests.Response.

Usage in a response_handler:
    @register_response_handler("wrap_auth")
    async def handle(ctx: RouteContext):
        body = ctx.response.body
        ctx.response.set_cookie("refresh_token", body["refresh_token"], httponly=True)
        ctx.response.keep_fields(["access_token", "expires_in"])
"""

from __future__ import annotations

import json
from typing import Any, Optional

from fastapi.responses import JSONResponse
from starlette.responses import Response
import requests


class ProxyResponseBuilder:
    """
    Builder for modifying a backend proxy response before returning to client.

    Methods intentionally limited — only controlled transformations are allowed.
    Handler cannot access raw requests.Response directly; use ctx.response.body
    for parsed body and builder methods for modifications.
    """

    def __init__(self, raw: requests.Response):
        self._raw = raw
        self._status_code: int = raw.status_code
        self._headers: dict[str, str] = dict(raw.headers)
        self._cookies: list[dict] = []
        self._body: Any = None
        self._passthrough: bool = False

    # ── passthrough ───────────────────────────────────

    def passthrough(self) -> None:
        """
        Mark response as passthrough — original proxy response returned unchanged.
        All other modifications are ignored if passthrough is set.
        """
        self._passthrough = True

    # ── status ────────────────────────────────────────

    @property
    def status_code(self) -> int:
        """Current status code (may have been modified)."""
        return self._status_code

    def set_status(self, code: int) -> None:
        """Override response status code."""
        self._status_code = code

    # ── headers ───────────────────────────────────────

    def set_header(self, key: str, value: str) -> None:
        """Set a response header."""
        self._headers[key] = value

    def remove_header(self, key: str) -> None:
        """Remove a response header."""
        self._headers.pop(key, None)

    # ── cookies ───────────────────────────────────────

    def set_cookie(self, key: str, value: str, **kwargs: Any) -> None:
        """
        Add a Set-Cookie header. Supports standard cookie attrs:
        httponly, secure, samesite, max_age, path, domain, expires.
        """
        cookie = {"key": key, "value": value}
        cookie.update(kwargs)
        self._cookies.append(cookie)

    # ── body ──────────────────────────────────────────

    @property
    def body(self) -> Any:
        """
        Parsed JSON body of the backend response (lazy, cached).
        Returns raw response content if not JSON.
        """
        try:
            return self._raw.json()
        except (ValueError, TypeError):
            return self._raw.content

    def set_body(self, data: Any) -> None:
        """Replace response body entirely. Must be JSON-serializable."""
        self._body = data

    def set_json(self, data: Any) -> None:
        """Alias for set_body()."""
        self.set_body(data)

    def merge_body(self, data: dict) -> None:
        """
        Merge fields into the JSON response body.
        Useful for adding extra fields without replacing the whole body.
        """
        current = self.body
        if isinstance(current, dict):
            current.update(data)
            self._body = current
        else:
            self._body = data

    def keep_fields(self, fields: list[str]) -> None:
        """
        Keep only the specified top-level fields in the JSON response body.
        All other fields are removed.
        """
        current = self.body
        if isinstance(current, dict):
            self._body = {k: v for k, v in current.items() if k in fields}

    def remove_fields(self, fields: list[str]) -> None:
        """
        Remove the specified top-level fields from the JSON response body.
        All other fields are preserved.
        """
        current = self.body
        if isinstance(current, dict):
            self._body = {k: v for k, v in current.items() if k not in fields}

    # ── finalize ──────────────────────────────────────

    def finalize(self) -> Response:
        """
        Build the final Starlette Response from accumulated modifications.

        - If passthrough is True: convert raw response directly.
        - Otherwise: apply status, headers, cookies, body modifications.
        """
        if self._passthrough:
            return self._raw_to_response(self._raw)

        if self._body is not None:
            body_data = self._body
        else:
            try:
                body_data = self._raw.json()
            except (ValueError, TypeError):
                return self._build_non_json_response()

        response = JSONResponse(content=body_data, status_code=self._status_code)

        for key, value in self._headers.items():
            response.headers[key] = value

        for cookie in self._cookies:
            key = cookie.pop("key")
            value = cookie.pop("value")
            response.set_cookie(key=key, value=value, **cookie)

        return response

    def _raw_to_response(self, resp: requests.Response) -> Response:
        """Convert raw requests.Response to Starlette Response (passthrough path)."""
        content_type = resp.headers.get("Content-Type", "application/json")
        try:
            data = resp.json()
            response = JSONResponse(content=data, status_code=resp.status_code)
        except (ValueError, TypeError):
            return Response(
                content=resp.content,
                status_code=resp.status_code,
                media_type=content_type,
            )
        for key, value in resp.headers.items():
            kl = key.lower()
            if kl not in ("content-encoding", "transfer-encoding", "content-length"):
                response.headers[key] = value
        return response

    def _build_non_json_response(self) -> Response:
        """Build a response for non-JSON backend body (passthrough style)."""
        content_type = self._raw.headers.get("Content-Type", "application/octet-stream")
        response = Response(
            content=self._raw.content,
            status_code=self._status_code,
            media_type=content_type,
        )
        for key, value in self._headers.items():
            response.headers[key] = value
        return response
