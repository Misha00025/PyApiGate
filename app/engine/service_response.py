"""
ServiceResponse — transport-agnostic wrapper around the HTTP response.

Mimics the API of requests.Response so users don't depend on the underlying
HTTP library (httpx). The engine can swap the transport layer without breaking
user code.
"""

from __future__ import annotations

from typing import Any

import httpx


class ServiceResponse:
    """Wrapper around httpx.Response that mimics requests.Response API.

    Public API matches requests.Response:
        .status_code, .headers, .content, .json(), .ok, .text, .url, .reason

    Internal (engine use only):
        ._raw — access to the underlying httpx.Response
    """

    def __init__(self, raw: httpx.Response):
        self._raw = raw

    # ── Public API (matches requests.Response) ──────────────

    @property
    def status_code(self) -> int:
        return self._raw.status_code

    @property
    def headers(self) -> dict[str, str]:
        return dict(self._raw.headers)

    @property
    def content(self) -> bytes:
        return self._raw.content

    def json(self) -> Any:
        return self._raw.json()

    @property
    def ok(self) -> bool:
        return self._raw.is_success

    @property
    def text(self) -> str:
        return self._raw.text

    @property
    def url(self) -> str:
        return str(self._raw.url)

    @property
    def reason(self) -> str:
        return self._raw.reason_phrase
