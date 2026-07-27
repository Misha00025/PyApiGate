# Authentication

Authentication is configured in `routes.yaml` under the global `auth` section. Per-route, set `auth: required` or `auth: none`.

## oauth2_jwt

Dynamically fetches signing keys from a JWKS endpoint. Supports key rotation with caching.

```yaml
auth:
  strategy: oauth2_jwt
  jwks_url: "${AUTH_SERVICE_URL}/.well-known/jwks.json"
  expected_issuer: "https://auth.example.com"
```

Validation: RS256 signature, `exp` claim, and optionally `iss`. Suitable for OIDC-compatible providers.

## rsa_jwt

Static RSA public key loaded from a PEM file.

```yaml
auth:
  strategy: rsa_jwt
  public_key_path: /certs/public.pem
  expected_issuer: "https://auth.example.com"
```

Validation: RS256 signature, `exp` claim.

## Custom Strategy

Register any validation logic in Python and reference it by name in YAML.

```python
from app.engine.registry import register_auth_strategy
from app.engine.models import AuthConfig

@register_auth_strategy("api_key")
def api_key_factory(config: AuthConfig):
    def _validate(ctx):
        key = ctx.request.headers.get("X-API-Key")
        if key == "my-secret":
            return {"userId": "service", "role": "admin"}
        return None
    return _validate
```

```yaml
auth:
  strategy: api_key
```

- The factory receives an `AuthConfig` instance and returns a validator function `(ctx) → dict | None`.
- Returning `None` results in a **401** response.
- Returning a `dict` sets `ctx.jwt` to that value.

## AuthConfig Model

| Field | Type | Description |
|-------|------|-------------|
| `strategy` | string | Strategy name |
| `public_key_path` | string | Path to PEM file (for `rsa_jwt`) |
| `jwks_url` | string | JWKS endpoint URL (for `oauth2_jwt`) |
| `expected_issuer` | string | Expected `iss` claim (optional) |
