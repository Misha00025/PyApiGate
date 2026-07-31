"""
RequestBuilder — controlled wrapper for modifying an outbound proxy request.

Created before each proxy request execution when a pre_request_handler is configured.
The handler receives the builder and modifies the request (headers, query params,
body, path) before it's sent to the backend service.

After the handler returns, the pipeline applies the accumulated modifications
to the actual HTTP request.
"""

from __future__ import annotations

from typing import Any, Optional


class RequestBuilder:
    """
    Builder for modifying a proxy request before sending to the backend.

    Created by the pipeline before calling the pre_request_handler.
    The handler receives the builder as a second argument and uses its
    methods to modify the outgoing request.

    Methods intentionally limited — only controlled transformations are allowed.
    """

    def __init__(self):
        self._headers: dict[str, str] = {}
        self._removed_headers: set[str] = set()
        self._query_params: dict[str, str] = {}
        self._removed_query_params: set[str] = set()
        self._body_override: Any = None
        self._body_merge: Optional[dict] = None
        self._path: Optional[str] = None

    # ── headers ───────────────────────────────────────

    def set_header(self, key: str, value: str) -> None:
        """Set a request header (overrides any existing value)."""
        self._headers[key] = value
        self._removed_headers.discard(key)

    def remove_header(self, key: str) -> None:
        """Remove a request header entirely."""
        self._removed_headers.add(key)
        self._headers.pop(key, None)

    # ── query params ──────────────────────────────────

    def set_query_param(self, key: str, value: str) -> None:
        """Set a query parameter (overrides any existing value)."""
        self._query_params[key] = value
        self._removed_query_params.discard(key)

    def remove_query_param(self, key: str) -> None:
        """Remove a query parameter entirely."""
        self._removed_query_params.add(key)
        self._query_params.pop(key, None)

    # ── body ──────────────────────────────────────────

    def set_body(self, data: Any) -> None:
        """Replace the request body entirely. Must be JSON-serializable."""
        self._body_override = data

    def set_json(self, data: Any) -> None:
        """Alias for set_body()."""
        self.set_body(data)

    def merge_body(self, data: dict) -> None:
        """
        Merge fields into the JSON request body.
        Useful for adding extra fields without replacing the whole body.
        Accumulates across multiple calls.
        """
        if self._body_merge is None:
            self._body_merge = {}
        self._body_merge.update(data)

    # ── path ──────────────────────────────────────────

    def set_path(self, path: str) -> None:
        """
        Override the proxy target path entirely.
        The path should be relative (e.g. /users/123).
        """
        self._path = path

    # ── empty check ───────────────────────────────────

    def is_empty(self) -> bool:
        """True if no modifications were made at all."""
        return (
            not self._headers
            and not self._removed_headers
            and not self._query_params
            and not self._removed_query_params
            and self._body_override is None
            and self._body_merge is None
            and self._path is None
        )
