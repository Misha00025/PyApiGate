"""
JWT-хелперы для PyApiGate.

Содержит только чистые функции для работы с JWT payload.
Никакой бизнес-логики, никаких обращений к сервисам.
"""
import jwt as pyjwt


def get_user_id(jwt_payload: dict | None) -> str | None:
    """Извлекает userId из JWT payload с fallback на sub (OIDC)."""
    if jwt_payload is None:
        return None
    return jwt_payload.get("userId") or jwt_payload.get("sub")


def get_group_id(jwt_payload: dict | None) -> str | None:
    """Извлекает groupId из JWT payload."""
    if jwt_payload is None:
        return None
    return jwt_payload.get("groupId")


def extract_ids(token: str) -> tuple[str | None, str | None]:
    """Извлекает userId и groupId из JWT БЕЗ проверки подписи (unsafe)."""
    payload = pyjwt.decode(token, options={"verify_signature": False})
    return payload.get("userId"), payload.get("groupId")
