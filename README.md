# PyApiGate

**Declarative YAML-driven API Gateway for FastAPI.**

Define routes, auth, access control, and proxy rules in a single YAML file — PyApiGate creates FastAPI endpoints, validates JWT tokens, calls your access/response handlers, and proxies requests to backend services.

- **Declarative** — routes, auth, access, and proxy in one YAML file
- **Pluggable auth** — `oauth2_jwt`, `rsa_jwt`, API keys, or anything else via AuthStrategy
- **Zero business logic** — the engine has no built-in domain code; all handlers are yours
- **Lightweight** — pure FastAPI, no heavy frameworks, no Docker required for development

---

## Quick Start

```bash
pip install -r requirements.txt
cp routes.example.yaml configs/routes.yaml
# настроить configs/routes.yaml под себя
python main.py
```

```bash
curl http://localhost:5000/hello
# {"status": "OK", "message": "Hello from PyApiGate!"}
```

---

## Route Configuration (configs/routes.yaml)

```yaml
base_path: ""                    # URL prefix for all routes (e.g. /v2)

services:                        # Backend services to proxy to
  users:  { base_url: "http://users:8000" }
  orders: { base_url: "http://orders:8000" }

routes:                          # Route definitions
  - path: /hello
    methods: [GET]
    handler: hello_handler
    auth: none
```

### Proxy Route

Forward requests directly to a backend service:

```yaml
- path: /groups/{group_id}/items
  methods: [GET, POST]
  proxy:
    service: users              # name from services section
    path: /groups/{group_id}/items
  auth: required
  access: group_member
```

### Handler Route

Custom logic orchestrated by your code:

```yaml
- path: /users/me
  methods: [GET]
  handler: whoami
  auth: required
```

### Multi-Method Format

Per-method configuration:

```yaml
- path: /groups/{group_id}
  methods:
    GET:
      proxy:
        service: campaign
        path: /groups/{group_id}
      auth: required
    PATCH:
      proxy:
        service: campaign
        path: /groups/{group_id}
      auth: required
      access: group_admin
```

### Fields Reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `path` | string | — | Route path with `{placeholders}` (e.g. `/users/{id}`) |
| `methods` | list/dict | `[GET]` | HTTP methods |
| `auth` | `"required"` / `"none"` | `"required"` | Whether JWT is required |
| `access` | string | `null` | Access handler name |
| `proxy` | object | `null` | Proxy config (see below) |
| `handler` | string | `null` | Response handler name |
| `params` | object | `null` | Parameter injection config |
| `description` | string | `null` | Human-readable description |

**Proxy config:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `service` | string | — | Backend service name |
| `path` | string | same as route | Target path with `{placeholder}` substitution |
| `skip_body` | bool | `false` | Don't forward the request body |
| `headers` | dict | `{}` | Extra headers for the proxied request |

---

## Writing Handlers

### Access Handlers (permission checks)

Synchronous — must return `ctx.allow()` or `ctx.deny()`:

```python
from app.engine.registry import register_access_handler
from app.engine.context import RouteContext

@register_access_handler("admin_only")
def check_admin(ctx: RouteContext):
    if ctx.jwt and ctx.jwt.get("role") == "admin":
        return ctx.allow()
    return ctx.deny()
```

### Response Handlers (custom responses)

Asynchronous — return a FastAPI `Response`:

```python
from app.engine.registry import register_response_handler
from app.engine.status import ok, not_found

@register_response_handler("get_user_profile")
async def handle_profile(ctx):
    user_id = ctx.path_params.get("user_id")
    resp = ctx.services.users.get(f"/profiles/{user_id}")
    if resp.status_code == 404:
        return not_found("User not found")
    return ok(resp.json())
```

### RouteContext

| Attribute | Type | Description |
|-----------|------|-------------|
| `ctx.request` | `Request` | FastAPI Request object |
| `ctx.path_params` | `dict` | URL parameters (e.g. `{"group_id": "123"}`) |
| `ctx.jwt` | `dict` or `None` | Decoded JWT payload |
| `ctx.services` | `ServiceRegistry` | HTTP clients for backend services |
| `ctx.state` | `dict` | Mutable storage between pipeline stages |

---

## Auth Strategy

Authentication is configured in YAML via the `auth` section.

### `oauth2_jwt` (recommended)

Dynamically fetches signing keys from the auth service's JWKS endpoint:

```yaml
auth:
  strategy: oauth2_jwt
  jwks_url: "${AUTH_SERVICE_URL}/.well-known/jwks.json"
  expected_issuer: "https://auth.example.com"
```

Keys are cached and support rotation. Token validation: RS256 signature, `exp`, and optionally `iss`.

### `rsa_jwt`

Static RSA public key loaded from a PEM file:

```yaml
auth:
  strategy: rsa_jwt
  public_key_path: /certs/public.pem
  expected_issuer: "https://auth.example.com"
```

### Custom strategy

Register any strategy in Python and reference it by name:

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

---

## Parameter Injection

Inject values from JWT, path, or query into proxied requests:

```yaml
params:
  query:
    userId: "{jwt.userId}"       # from JWT payload
    groupId: "{path.group_id}"   # from URL parameter
  body:
    owner_id: "{jwt.userId}"     # inject into JSON body
```

Shorthand `params.query: "*"` forwards all incoming query parameters plus `userId` from JWT.

---

## Docker

```bash
docker build -t pyapi-gate .
docker run -p 5000:5000 \
  -v /path/to/configs/routes.yaml:/app/configs/routes.yaml \
  -e CONFIG_PATH=/app/configs/routes.yaml \
  pyapi-gate
```
