# PyApiGate

**Declarative YAML-driven API Gateway for FastAPI.**

Define routes, auth, access control, and proxy rules in a single YAML file — PyApiGate creates FastAPI endpoints, validates JWT tokens, calls your access/response handlers, and proxies requests to backend services.

- **Declarative** — routes, auth, access, proxy in one YAML file
- **Pluggable auth** — oauth2_jwt, rsa_jwt, API keys, or custom strategies
- **Zero business logic** — the engine has no built-in domain code; all handlers are yours
- **Lightweight** — pure FastAPI, no heavy frameworks

---

## Quick Start

```bash
pip install -r requirements.txt
cp configs_default/routes.yaml configs/routes.yaml
# edit configs/routes.yaml to match your services
python main.py
```

```bash
curl http://localhost:5000/hello
# {"status": "OK", "message": "Hello from PyApiGate!"}
```

---

## Documentation

| Topic | File |
|-------|------|
| Getting Started | [docs/getting-started.md](docs/getting-started.md) |
| Route Configuration | [docs/route-configuration.md](docs/route-configuration.md) |
| Writing Handlers | [docs/writing-handlers.md](docs/writing-handlers.md) |
| Authentication | [docs/authentication.md](docs/authentication.md) |
| Parameter Injection | [docs/parameter-injection.md](docs/parameter-injection.md) |
| Application Configuration | [docs/configuration.md](docs/configuration.md) |
| Request Pipeline | [docs/pipeline.md](docs/pipeline.md) |
| Deployment | [docs/deployment.md](docs/deployment.md) |

## Route Types

**Proxy route** — forwards requests to a backend service:

```yaml
- path: /api/users/{id}
  methods: [GET]
  proxy:
    service: users
    path: /users/{id}
  auth: required
```

**Handler route** — executes custom Python logic:

```yaml
- path: /users/me
  methods: [GET]
  handler: whoami
  auth: required
```

See [Route Configuration](docs/route-configuration.md) for all options.

---

## Writing Handlers

**Access handlers** check permissions (synchronous, must return `allow()` / `deny()`).  
**Response handlers** generate responses (asynchronous, return a Starlette Response).

```python
@register_access_handler("admin_only")
def check_admin(ctx: RouteContext):
    if ctx.jwt and ctx.jwt.get("role") == "admin":
        return ctx.allow()
    return ctx.deny()
```

See [Writing Handlers](docs/writing-handlers.md) for the full API.

---

## Authentication

Configured globally in `routes.yaml`:

```yaml
auth:
  strategy: oauth2_jwt
  jwks_url: "${AUTH_SERVICE_URL}/.well-known/jwks.json"
  expected_issuer: "https://auth.example.com"
```

Available strategies: `oauth2_jwt` (JWKS), `rsa_jwt` (static PEM), or custom.

See [Authentication](docs/authentication.md) for all options.
