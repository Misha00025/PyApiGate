"""
Встроенные стратегии аутентификации для PyApiGate.
"""
from __future__ import annotations

from typing import Optional
import jwt as pyjwt

from app.engine.context import RouteContext
from app.engine.models import AuthConfig
from app.engine.registry import register_auth_strategy


def rsa_jwt_auth_strategy(public_key: str, expected_issuer: Optional[str] = None):
    """
    Создаёт стратегию аутентификации на основе RSA JWT.

    Args:
        public_key: RSA public key в PEM-формате.
        expected_issuer: Опциональный OAuth issuer для проверки iss claim.

    Returns:
        Функция auth_strategy для передачи в create_app().
    """
    def _validate(ctx: RouteContext) -> Optional[dict]:
        raw_token = ctx.request.headers.get("Authorization")
        if not raw_token:
            return None

        token = raw_token
        if token.startswith("Bearer "):
            token = token[7:]

        try:
            options = {
                "verify_signature": True,
                "verify_exp": True,
                "verify_aud": False,
            }
            payload = pyjwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                options=options,
            )

            if expected_issuer and payload.get("iss") and payload["iss"] != expected_issuer:
                return None

            return payload
        except pyjwt.PyJWTError:
            return None

    return _validate


@register_auth_strategy("rsa_jwt")
def _rsa_jwt_factory(config: AuthConfig):
    """Фабрика для rsa_jwt стратегии из YAML-конфига."""
    if not config.public_key_path:
        raise ValueError("public_key_path required for rsa_jwt strategy")

    with open(config.public_key_path, "rb") as f:
        public_key = f.read()

    return rsa_jwt_auth_strategy(public_key, expected_issuer=config.expected_issuer)
