"""
Встроенные стратегии аутентификации для PyApiGate.
"""
from __future__ import annotations

from typing import Optional
import jwt as pyjwt

from app.engine.context import RouteContext


def rsa_jwt_auth_strategy(public_key: str, oidc_issuer: Optional[str] = None):
    """
    Создаёт стратегию аутентификации на основе RSA JWT.

    Args:
        public_key: RSA public key в PEM-формате.
        oidc_issuer: Опциональный OIDC issuer для проверки iss claim.

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

            if oidc_issuer and payload.get("iss") and payload["iss"] != oidc_issuer:
                return None

            return payload
        except pyjwt.PyJWTError:
            return None

    return _validate
