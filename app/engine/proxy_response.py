"""
ResponseBuilder — controlled wrapper for modifying any pipeline response.

Created at the start of every request pipeline. Any handler (access, response,
proxy response) can accumulate modifications. At the end of the pipeline, 
modifications are applied to the response.

For proxy routes with response_handler: builder gets a base (raw requests.Response)
before the handler is called, and finalize() creates the Starlette Response.

For all other routes: apply_to() overlays builder modifications (headers, cookies,
body) onto the response returned by the handler or proxy.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from fastapi.responses import JSONResponse
from starlette.responses import Response
import requests


class ResponseBuilder:
    """
    Builder for modifying a pipeline response.

    Created at the start of every request pipeline in execute_pipeline().
    Accumulates modifications that are applied after the execute step.

    Methods intentionally limited — only controlled transformations are allowed.
    """

    def __init__(self):
        self._base: Optional[requests.Response] = None
        self._status_code: Optional[int] = None
        self._headers: dict[str, str] = {}
        self._removed_headers: set[str] = set()
        self._cookies: list[dict] = []
        self._body_override: Any = None
        self._merge: Optional[dict] = None
        self._keep: Optional[list[str]] = None
        self._remove: Optional[list[str]] = None
        self._passthrough: bool = False

    # ── base ─────────────────────────────────────────

    def set_base(self, raw: requests.Response) -> None:
        """Set the backend response as source for body operations.

        Called by pipeline after _execute_proxy_raw() for proxy + response_handler routes.
        """
        self._base = raw
        if self._status_code is None:
            self._status_code = raw.status_code

    def has_base(self) -> bool:
        """Whether a base (backend response) has been set."""
        return self._base is not None

    # ── body (property) ──────────────────────────────

    @property
    def body(self) -> Any:
        """
        Parsed JSON body of the base backend response (lazy, cached by requests).

        Raises RuntimeError if base is not set yet (only available during proxy
        response handler, after the proxy request).
        """
        if self._base is None:
            raise RuntimeError("Response body is not available yet — only accessible after proxy execution")
        try:
            return self._base.json()
        except (ValueError, TypeError):
            return self._base.content

    # ── status ───────────────────────────────────────

    @property
    def status_code(self) -> Optional[int]:
        """Current status code (may have been modified, or None if not set)."""
        if self._status_code is not None:
            return self._status_code
        if self._base is not None:
            return self._base.status_code
        return None

    def set_status(self, code: int) -> None:
        """Override response status code."""
        self._status_code = code

    # ── passthrough ───────────────────────────────────

    def passthrough(self) -> None:
        """Mark as passthrough — original proxy response returned unchanged.

        Only relevant for proxy routes with response_handler.
        For other routes this is a no-op.
        """
        self._passthrough = True

    # ── headers ───────────────────────────────────────

    def set_header(self, key: str, value: str) -> None:
        """Set a response header."""
        self._headers[key] = value
        self._removed_headers.discard(key)

    def remove_header(self, key: str) -> None:
        """Remove a response header."""
        self._removed_headers.add(key)
        self._headers.pop(key, None)

    # ── cookies ───────────────────────────────────────

    def set_cookie(self, key: str, value: str, **kwargs: Any) -> None:
        """
        Add a Set-Cookie header. Supports standard cookie attrs:
        httponly, secure, samesite, max_age, path, domain, expires.
        """
        self._cookies.append({"key": key, "value": value, **kwargs})

    # ── body modifications ───────────────────────────

    def set_body(self, data: Any) -> None:
        """Replace response body entirely. Must be JSON-serializable."""
        self._body_override = data

    def set_json(self, data: Any) -> None:
        """Alias for set_body()."""
        self.set_body(data)

    def merge_body(self, data: dict) -> None:
        """
        Merge fields into the JSON response body.
        Useful for adding extra fields without replacing the whole body.
        Accumulates across multiple calls.
        """
        if self._merge is None:
            self._merge = {}
        self._merge.update(data)

    def keep_fields(self, fields: list[str]) -> None:
        """
        Keep only the specified top-level fields in the JSON response body.
        Mutually exclusive with remove_fields (last one wins).
        """
        self._keep = fields
        self._remove = None

    def remove_fields(self, fields: list[str]) -> None:
        """
        Remove the specified top-level fields from the JSON response body.
        Mutually exclusive with keep_fields (last one wins).
        """
        self._remove = fields
        self._keep = None

    # ── empty check ──────────────────────────────────

    def is_empty(self) -> bool:
        """True if no modifications were made at all."""
        return (
            self._status_code is None
            and not self._headers
            and not self._removed_headers
            and not self._cookies
            and self._body_override is None
            and self._merge is None
            and self._keep is None
            and self._remove is None
            and not self._passthrough
        )

    # ── output: finalize / apply_to ──────────────────

    def finalize(self) -> Response:
        """
        Build a Starlette Response from base + accumulated modifications.

        Used for proxy + response_handler routes where the handler does
        not return a Response — the builder owns the full response construction.

        Raises RuntimeError if base is not set.
        """
        if self._base is None:
            raise RuntimeError("Cannot finalize: no base response set")

        if self._passthrough:
            return self._raw_to_response(self._base)

        body_data = self._resolve_body()
        status = self._status_code if self._status_code is not None else self._base.status_code

        if isinstance(body_data, bytes):
            content_type = self._base.headers.get("Content-Type", "application/octet-stream")
            response = Response(content=body_data, status_code=status, media_type=content_type)
        else:
            response = JSONResponse(content=body_data, status_code=status)

        return self._apply_overlay(response)

    def apply_to(self, response: Response) -> Response:
        """
        Overlay builder modifications onto an existing Starlette Response.

        Used for all non-finalized paths (handler routes, plain proxy routes).
        Applies headers, cookies, status code, and body modifications on top.
        """
        if self.is_empty() or self._passthrough:
            return response

        if self._body_override is not None:
            response = JSONResponse(content=self._body_override, status_code=response.status_code)
        elif self._base is not None:
            body_data = self._resolve_body()
            if body_data is not None and not isinstance(body_data, bytes):
                response = JSONResponse(content=body_data, status_code=response.status_code)
        elif self._merge is not None or self._keep is not None or self._remove is not None:
            try:
                current = json.loads(response.body)
                if isinstance(current, dict):
                    modified = dict(current)
                    if self._keep is not None:
                        modified = {k: v for k, v in modified.items() if k in self._keep}
                    elif self._remove is not None:
                        modified = {k: v for k, v in modified.items() if k not in self._remove}
                    if self._merge:
                        modified.update(self._merge)
                    response = JSONResponse(content=modified, status_code=response.status_code)
            except (ValueError, TypeError):
                pass

        return self._apply_overlay(response)

    # ── internal helpers ─────────────────────────────

    def _resolve_body(self) -> Any:
        """Resolve final body from base + body modifications."""
        if self._body_override is not None:
            return self._body_override

        if self._base is None:
            return None

        try:
            data = self._base.json()
        except (ValueError, TypeError):
            return self._base.content

        if isinstance(data, dict):
            if self._keep is not None:
                data = {k: v for k, v in data.items() if k in self._keep}
            elif self._remove is not None:
                data = {k: v for k, v in data.items() if k not in self._remove}
            if self._merge:
                data.update(self._merge)

        return data

    def _apply_overlay(self, response: Response) -> Response:
        """Apply headers, cookies, and status code onto a response object."""
        if self._status_code is not None:
            response.status_code = self._status_code

        for key in self._removed_headers:
            try:
                del response.headers[key]
            except (KeyError, TypeError, AttributeError):
                pass

        for key, value in self._headers.items():
            response.headers[key] = value

        for cookie in self._cookies:
            c = dict(cookie)
            k = c.pop("key")
            v = c.pop("value")
            response.set_cookie(key=k, value=v, **c)

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
