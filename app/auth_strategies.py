"""
Built-in authentication strategies for PyApiGate.
"""
from __future__ import annotations

from typing import Optional
import jwt as pyjwt
from jwt import PyJWKClient, PyJWTError

from app.engine.context import RouteContext
from app.engine.models import AuthConfig
from app.engine.registry import register_auth_strategy


def rsa_jwt_auth_strategy(public_key: str, expected_issuer: Optional[str] = None):
    """
    Creates an RSA JWT authentication strategy.

    Args:
        public_key: RSA public key in PEM format.
        expected_issuer: Optional OAuth issuer for checking the iss claim.

    Returns:
        auth_strategy function for passing to create_app().
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
    """Factory for rsa_jwt strategy from YAML config."""
    if not config.public_key_path:
        raise ValueError("public_key_path required for rsa_jwt strategy")

    with open(config.public_key_path, "rb") as f:
        public_key = f.read()

    return rsa_jwt_auth_strategy(public_key, expected_issuer=config.expected_issuer)


@register_auth_strategy("oauth2_jwt")
def _oauth2_jwt_factory(config: AuthConfig):
    """
    OAuth2 JWT strategy via JWKS endpoint.

    Fetches public keys dynamically from the auth service's JWKS endpoint
    and validates JWT tokens against them.
    Supports RS256 and key rotation.

    Config:
        jwks_url: URL to JWKS endpoint (e.g. http://auth:8000/.well-known/jwks.json)
        expected_issuer: Optional iss claim validation
    """
    if not config.jwks_url:
        raise ValueError("jwks_url required for oauth2_jwt strategy")

    jwks_client = PyJWKClient(
        config.jwks_url,
        cache_keys=True,
        max_cached_keys=10,
    )

    def _validate(ctx) -> Optional[dict]:
        raw_token = ctx.request.headers.get("Authorization")
        if not raw_token:
            return None

        token = raw_token
        if token.startswith("Bearer "):
            token = token[7:]

        if not token:
            return None

        try:
            signing_key = jwks_client.get_signing_key_from_jwt(token)

            options = {
                "verify_signature": True,
                "verify_exp": True,
                "verify_aud": False,
            }
            payload = pyjwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                options=options,
            )

            if config.expected_issuer and payload.get("iss") and payload["iss"] != config.expected_issuer:
                return None

            return payload
        except PyJWTError:
            return None

    return _validate
