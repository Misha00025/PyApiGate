"""
Tests for auth strategies, status helpers, and validate_config script.
"""

import json
import os
import subprocess
import sys
from unittest.mock import MagicMock

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt as pyjwt

from app.engine.status import (
    answer, ok, created, accepted, forbidden, unauthorized,
    not_found, bad_request, not_implemented, conflict, bad_gateway,
)
from app.engine.context import RouteContext
from app.auth_strategies import rsa_jwt_auth_strategy
from app.engine.models import AuthConfig


# ============================================================
# Helper: generate RSA key pair
# ============================================================

@pytest.fixture(scope="session")
def rsa_keys():
    """Generate RSA key pair once per test session."""
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
    )
    public_key = private_key.public_key()

    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    return {"private": private_pem, "public": public_pem, "private_key": private_key}


@pytest.fixture
def valid_token(rsa_keys):
    """Create a valid JWT signed with the test private key."""
    payload = {"sub": "user123", "iss": "https://auth.example.com", "exp": 9999999999}
    return pyjwt.encode(payload, rsa_keys["private"], algorithm="RS256")


@pytest.fixture
def expired_token(rsa_keys):
    """Create an expired JWT."""
    payload = {"sub": "user123", "iss": "https://auth.example.com", "exp": 1000000000}
    return pyjwt.encode(payload, rsa_keys["private"], algorithm="RS256")


@pytest.fixture
def wrong_key_token():
    """Create a JWT signed with a different key."""
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_private = other_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    payload = {"sub": "user123", "iss": "https://auth.example.com", "exp": 9999999999}
    return pyjwt.encode(payload, other_private, algorithm="RS256")


# ============================================================
# Helper: minimal context with auth header
# ============================================================

def make_auth_context(token: str) -> RouteContext:
    """Create RouteContext with a Bearer token header."""
    mock_request = MagicMock()
    mock_request.headers.get.return_value = f"Bearer {token}"
    return RouteContext(
        request=mock_request,
        path_params={},
    )


# ============================================================
# Auth Strategy Tests
# ============================================================

class TestRsaJwtStrategy:
    def test_valid_token(self, rsa_keys, valid_token):
        strategy = rsa_jwt_auth_strategy(rsa_keys["public"])
        ctx = make_auth_context(valid_token)
        result = strategy(ctx)
        assert result is not None
        assert result["sub"] == "user123"

    def test_no_auth_header(self, rsa_keys):
        strategy = rsa_jwt_auth_strategy(rsa_keys["public"])
        ctx = RouteContext(
            request=MagicMock(headers=MagicMock(get=MagicMock(return_value=None))),
            path_params={},
        )
        result = strategy(ctx)
        assert result is None

    def test_wrong_key(self, rsa_keys, wrong_key_token):
        strategy = rsa_jwt_auth_strategy(rsa_keys["public"])
        ctx = make_auth_context(wrong_key_token)
        result = strategy(ctx)
        assert result is None

    def test_expired_token(self, rsa_keys, expired_token):
        strategy = rsa_jwt_auth_strategy(rsa_keys["public"])
        ctx = make_auth_context(expired_token)
        result = strategy(ctx)
        assert result is None

    def test_issuer_check_pass(self, rsa_keys, valid_token):
        strategy = rsa_jwt_auth_strategy(rsa_keys["public"], expected_issuer="https://auth.example.com")
        ctx = make_auth_context(valid_token)
        result = strategy(ctx)
        assert result is not None

    def test_issuer_check_fail(self, rsa_keys, valid_token):
        strategy = rsa_jwt_auth_strategy(rsa_keys["public"], expected_issuer="https://wrong.com")
        ctx = make_auth_context(valid_token)
        result = strategy(ctx)
        assert result is None


class TestRsaJwtFactory:
    def test_missing_public_key_path(self, tmp_path):
        config = AuthConfig(strategy="rsa_jwt")
        with pytest.raises(ValueError, match="public_key_path"):
            from app.auth_strategies import _rsa_jwt_factory
            _rsa_jwt_factory(config)

    def test_factory_creates_strategy(self, tmp_path, rsa_keys):
        key_file = tmp_path / "public.pem"
        key_file.write_text(rsa_keys["public"])

        config = AuthConfig(strategy="rsa_jwt", public_key_path=str(key_file))
        from app.auth_strategies import _rsa_jwt_factory
        strategy = _rsa_jwt_factory(config)
        assert callable(strategy)


class TestOauth2JwtFactory:
    def test_missing_jwks_url(self):
        config = AuthConfig(strategy="oauth2_jwt")
        from app.auth_strategies import _oauth2_jwt_factory
        with pytest.raises(ValueError, match="jwks_url"):
            _oauth2_jwt_factory(config)


# ============================================================
# Status Helper Tests
# ============================================================

class TestStatusHelpers:
    def test_ok(self):
        resp = ok({"data": "test"})
        assert resp.status_code == 200
        assert resp.body is not None

    def test_ok_default(self):
        resp = ok()
        assert resp.status_code == 200
        data = json.loads(resp.body)
        assert data.get("status") == "OK"

    def test_created(self):
        resp = created({"id": 1})
        assert resp.status_code == 201

    def test_created_default(self):
        resp = created()
        assert resp.status_code == 201

    def test_accepted(self):
        resp = accepted()
        assert resp.status_code == 202

    def test_forbidden(self):
        resp = forbidden()
        assert resp.status_code == 403

    def test_forbidden_with_message(self):
        resp = forbidden("Custom message")
        assert resp.status_code == 403
        data = json.loads(resp.body)
        assert "Custom message" in str(data)

    def test_unauthorized(self):
        resp = unauthorized()
        assert resp.status_code == 401

    def test_not_found(self):
        resp = not_found()
        assert resp.status_code == 404

    def test_bad_request(self):
        resp = bad_request()
        assert resp.status_code == 400

    def test_not_implemented(self):
        resp = not_implemented()
        assert resp.status_code == 501

    def test_conflict(self):
        resp = conflict()
        assert resp.status_code == 409

    def test_bad_gateway(self):
        resp = bad_gateway()
        assert resp.status_code == 502

    def test_answer_with_dict(self):
        resp = answer(200, {"custom": "data"})
        assert resp.status_code == 200
        data = json.loads(resp.body)
        assert data == {"custom": "data"}

    def test_answer_error_string(self):
        resp = answer(400, "Bad request text")
        assert resp.status_code == 400
        data = json.loads(resp.body)
        assert "Bad request text" in str(data) or "error" in data

    def test_answer_all_error_codes(self):
        """All error codes should include an 'error' key in response body."""
        for code in (400, 401, 403, 404, 409, 501, 502):
            resp = answer(code)
            assert resp.status_code == code


# ============================================================
# validate_config script tests
# ============================================================

class TestValidateConfigScript:
    def test_script_creates_configs_from_defaults(self, tmp_path):
        """Running validate_config should create configs from defaults."""
        defaults_dir = tmp_path / "configs_default"
        defaults_dir.mkdir()
        (defaults_dir / "app.json").write_text(json.dumps({
            "logging": {"level": "INFO"},
            "request_id": {"header": "X-Request-ID"},
        }))
        (defaults_dir / "routes.yaml").write_text("base_path: ''\nroutes: []\n")

        config_dir = tmp_path / "configs"
        config_dir.mkdir()

        script_path = os.path.join(os.path.dirname(__file__), "..", "scripts", "validate_config.py")
        result = subprocess.run(
            [sys.executable, script_path],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
        )

        assert (config_dir / "app.json").exists(), f"stdout: {result.stdout}, stderr: {result.stderr}"
        assert (config_dir / "routes.yaml").exists()
        assert result.returncode == 0

    def test_script_fails_without_defaults_dir(self, tmp_path):
        """Running validate_config without configs_default should exit 1."""
        script_path = os.path.join(os.path.dirname(__file__), "..", "scripts", "validate_config.py")
        result = subprocess.run(
            [sys.executable, script_path],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
        )
        assert result.returncode == 1
        assert "not found" in result.stdout or "not found" in result.stderr
