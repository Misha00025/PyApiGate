# PyApiGate

**Declarative YAML-driven API Gateway for Flask.**

Define your routes, access control, and proxy rules in a single YAML file — PyApiGate creates Flask endpoints, validates JWT tokens, calls your access/response handlers, and proxies requests to backend services.

```yaml
# routes.yaml
services:
  users: { base_url: "http://users-api:8000" }

routes:
  - path: /users/{id}
    methods: [GET, PUT]
    proxy:
      service: users
      path: /users/{id}
    auth: required
    access:
      GET: everyone
      PUT: owner_only
```

---

## Quick Start

```bash
pip install -r req.txt
cp routes.example.yaml routes.yaml
# настроить routes.yaml под себя
python main.py
```

---

## Your First Route

### 1. Create `routes.yaml`

```yaml
base_path: ""

services:
  my_api:
    base_url: "http://localhost:8080"

routes:
  - path: /hello
    methods: [GET]
    handler: hello_handler
    auth: none
```

### 2. Write a handler

```python
# handlers/hello.py
from app.engine.registry import register_response_handler
from app.engine.status import ok

@register_response_handler("hello_handler")
def hello_handler(ctx):
    return ok({"message": "Hello from PyApiGate!"})
```

To use handlers, create a `handlers/` directory with an `__init__.py` that imports your handler modules, then import the handlers package before calling `create_app()`.

### 3. Run

```bash
python main.py
curl http://localhost:5000/hello
# {"status": "OK", "message": "Hello from PyApiGate!"}
```

---

## Route Configuration (routes.yaml)

### Basics

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
    path: /groups/{group_id}/items   # target path (supports {placeholders})
  auth: required
  access:
    GET: group_member
    POST: group_admin
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
| `path` | string | — | Flask route path (e.g. `/users/<int:id>`) |
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

```python
from app.engine.registry import register_response_handler
from app.engine.status import ok, created, not_found

@register_response_handler("get_user_profile")
def handle_profile(ctx):
    user_id = ctx.path_params.get("user_id")
    resp = ctx.services.users.get(f"/profiles/{user_id}")
    if resp.status_code == 404:
        return not_found("User not found")
    return ok(resp.json())
```

### Handler Conventions

- Create a `handlers/` package with an `__init__.py` that imports your handler modules, then import the package before calling `create_app()`.
- Handlers receive a `RouteContext` with access to request, JWT, path params, and backend services.
- Access handlers return `ctx.allow()` or `ctx.deny()`.
- Response handlers return a Flask `Response` (use helpers from `app.engine.status`).

---

## RouteContext

The context object passed to every handler:

```python
ctx.request         # Flask Request object
ctx.path_params     # URL parameters (e.g. {"group_id": "123"})
ctx.jwt             # Decoded JWT payload (dict) or None
ctx.services        # ServiceRegistry — HTTP clients for backends
ctx.state           # Mutable dict to pass data between pipeline stages

# Built-in helpers
ctx.allow()         # -> AccessResult(allowed=True)
ctx.deny(response)  # -> AccessResult(allowed=False, response=response)
ctx.deny()          # -> 403 Forbidden
```

---

## Auth Strategy

Authentication is configured in YAML via the `auth` section:

```yaml
auth:
  strategy: rsa_jwt
  public_key_path: /certs/public.pem
  expected_issuer: "https://auth.example.com"
```

PyApiGate ships with built-in strategies (`rsa_jwt`). To use a custom strategy, register it in Python before calling `create_app()`:

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

Once registered, reference it in YAML by name:

```yaml
auth:
  strategy: api_key
```

`create_app()` now takes no auth parameters:

```python
from app import create_app
app = create_app(config_path="routes.yaml")
```

---

## Parameter Injection

Inject values from JWT, path, or query into proxied requests:

```yaml
params:
  query:
    userId: "{jwt.userId}"       # from JWT payload
    groupId: "{path.group_id}"   # from URL parameter
    "*": query                   # forward all other query params as-is
  body:
    owner_id: "{jwt.userId}"     # inject into JSON body
```

Shorthand `params.query: "*"` forwards all incoming query parameters plus `userId` from JWT.

---

## ServiceRegistry

Access backend services from response handlers:

```python
# Define in routes.yaml:
# services:
#   users:  { base_url: "http://users-api:8000" }
#   orders: { base_url: "http://orders-api:8000" }

# In your handler:
resp = ctx.services.users.get("/profiles/42")
resp = ctx.services.orders.post("/checkout", json={"cart": [...]})
```

Available methods: `.get()`, `.post()`, `.put()`, `.patch()`, `.delete()`, `.request()`.

---

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `CONFIG_PATH` | Path to routes.yaml | `routes.yaml` |

Services in `routes.yaml` support `${ENV_VAR}` and `${ENV_VAR:-default}` substitution.

---

## Project Structure

```
PyApiGate/
├── app/
│   ├── __init__.py              # create_app() — Flask app factory
│   ├── auth_strategies.py       # Built-in auth strategies (RSA JWT, ...)
│   ├── security.py              # JWT helpers: get_user_id()
│   └── engine/
│       ├── models.py            # RouteConfig, GatewayConfig, ProxyConfig, ...
│       ├── context.py           # RouteContext, AccessResult
│       ├── registry.py          # ServiceRegistry, handler registries + decorators
│       ├── loader.py            # YAML parser → GatewayConfig
│       ├── pipeline.py          # Auth → Access → Execute
│       ├── proxy.py             # HTTP proxy + parameter injection
│       ├── bootstrap.py         # YAML → Blueprint → Flask
│       └── status.py            # HTTP response helpers (ok, forbidden, ...)
├── main.py                      # Dev server
├── wsgi.py                      # Gunicorn entrypoint
├── Dockerfile
├── req.txt
├── routes.example.yaml          # Template config
└── tests/
    ├── conftest.py
    ├── test_routes.yaml
    ├── test_engine_unit.py
    └── test_handlers.py
```

---

## Running Tests

```bash
pip install pytest
python -m pytest tests/ -v
```

All 16 tests pass in ~0.08s with no external dependencies or Docker.

---

## Docker

```bash
docker build -t pyapi-gate .
docker run -p 5000:5000 \
  -v /path/to/routes.yaml:/app/routes.yaml \
  -e CONFIG_PATH=/app/routes.yaml \
  pyapi-gate
```

---

## Why PyApiGate?

- **Declarative** — routes, auth, access, and proxy rules in one YAML file
- **Pluggable auth** — swap RSA JWT for API keys, OIDC, or anything else via AuthStrategy
- **Zero business logic** — the engine has no built-in domain code; all handlers are yours
- **Lightweight** — pure Flask, no heavy frameworks, no Docker required for development
- **Testable** — unit tests run in milliseconds without infrastructure

---

## Migrating from TDN

If you are migrating from TheDungeonNotebook's API Gateway, note the following differences:

- **`_sanitize_user_params` is removed.** In TDN, a `before_request` hook stripped `userId` and `access` from query parameters. PyApiGate does not do this — if you need similar behaviour, add your own `before_request` handler.
- **Auto-import of `handlers/` is removed.** You must explicitly import your handlers package before calling `create_app()`.
- **`base_path` default is now `""`** (previously `"/v2"`).
- **`access` field is now a string only** (dictionary per-method access is no longer supported; use the multi-method YAML format instead).
- **`ResponseTransform` and `ResponseConfig` are removed.** Use response handlers for any custom response logic.
