"""
Custom logging formatter that resolves source expressions ({jwt.field}, {path.field}, {query.field})
from the request-scoped logging context.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from app.logging_context import resolve_source


SOURCE_PATTERN = re.compile(r"\{[a-zA-Z_]+\.[a-zA-Z_]+\}")


class SourceExpressionFormatter(logging.Formatter):
    """
    Logging formatter that resolves {jwt.field}, {path.field}, {query.field}
    expressions from the per-request logging context.

    If a source is missing or no request context is active, substitutes "-".
    All other format specifiers (%(...)s) are handled by the parent class normally.
    """

    def format(self, record: logging.LogRecord) -> str:
        fmt = self._fmt or "%(message)s"

        def _replace(match: re.Match) -> str:
            return resolve_source(match.group(0))

        resolved_fmt = SOURCE_PATTERN.sub(_replace, fmt)

        temp_formatter = logging.Formatter(resolved_fmt, self.datefmt)
        return temp_formatter.format(record)
