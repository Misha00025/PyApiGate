"""
JWT helpers for PyApiGate.

Contains pure functions for working with JWT payload.
No business logic, no service calls.
"""


def get_user_id(jwt_payload: dict | None) -> str | None:
    """Extracts userId from JWT payload with fallback to sub (OIDC)."""
    if jwt_payload is None:
        return None
    return jwt_payload.get("userId") or jwt_payload.get("sub")
