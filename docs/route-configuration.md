# Route Configuration

`routes.yaml` is the main configuration file. All string values support environment variable substitution with `${ENV_VAR}` (required) and `${ENV_VAR:-default}` (with fallback).

> See [`configs_default/routes.yaml`](../configs_default/routes.yaml) for a complete working example.

## Global Sections

### `base_path`

URL prefix applied to all routes.

```yaml
base_path: "/v2"
```

### `auth`

Global authentication configuration. See [Authentication](authentication.md).

### `services`

Backend service definitions.

```yaml
services:
  users:
    base_url: "http://users:8000"
    timeout: 30
  orders:
    base_url: "http://orders:8000"
```

- `base_url` — base URL of the backend service
- `timeout` (optional) — request timeout in seconds (default: 30)

## Route: Basic Structure

```yaml
- path: /hello
  methods: [GET]
  handler: hello_handler
  auth: none
  description: "Hello world"
```

## Proxy Route

Forward requests directly to a backend service.

```yaml
- path: /api/users/{user_id}
  methods: [GET, PUT]
  proxy:
    service: users
    path: /users/{user_id}
  auth: required
  access: group_member
  params:
    query: "*"
```

## Handler Route

Execute custom response handler logic.

```yaml
- path: /users/me
  methods: [GET]
  handler: whoami
  auth: required
```

> **Note:** `handler` and `proxy` are mutually exclusive. If both are set, `handler` takes priority and the route will not proxy. For proxy routes that need response modification, use `response_handler` instead.

## Proxy Route with Response Handler

Execute a response handler **after** the proxy request to modify the backend response.

```yaml
- path: /auth/token
  methods: [POST]
  proxy:
    service: auth
    path: /token
  response_handler: wrap_auth_response
  response:
    wrap: data
```

The pipeline is: `proxy → response_handler → wrap` — the handler modifies the response via `ctx.response` (a `ResponseBuilder`). See [ResponseBuilder](writing-handlers.md#responsebuilder--modifying-any-response-asynchronous).

> **Note:** Unlike `handler`, `response_handler` does **not** replace `proxy` — it complements it. The proxy request is always executed, and the handler only modifies the response.

## Proxy Route with Pre-Request Handler

Execute a pre-request handler **before** the proxy request to modify the outgoing request.

```yaml
- path: /api/users/{user_id}
  methods: [GET, PUT]
  proxy:
    service: users
    path: /users/{user_id}
  pre_request_handler: add_auth_header
  auth: required
  params:
    query: "*"
```

The pipeline is: `auth → access → pre_request_handler → proxy → response_handler (if any) → wrap`. The handler receives a `RequestBuilder` and can modify headers, query params, body, and target path. See [Pre-Request Handlers](writing-handlers.md#pre-request-handlers-asynchronous).

> **Note:** `pre_request_handler` only applies to routes with `proxy`. It is ignored for handler-only routes.

## Multi-Method Routes

Different configuration per HTTP method.

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

## Flask-Compatible URLs

Flask-style `<int:user_id>` notation is automatically converted to `{user_id}`.

> **Important:** FastAPI path parameters are always strings. If you need integer comparison, cast explicitly: `int(ctx.path_params["group_id"])`.

## Fields Reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `path` | string | — | Route path with `{placeholders}` |
| `methods` | list/dict | `[GET]` | HTTP methods |
| `auth` | `"required"` / `"none"` | `"required"` | Whether JWT is required |
| `access` | string | `null` | Access handler name |
| `pre_request_handler` | string | `null` | Pre-request handler name — modifies the outgoing proxy request before it's sent. See [Pre-Request Handlers](writing-handlers.md#pre-request-handlers-asynchronous) |
| `proxy` | object | `null` | Proxy configuration |
| `response_handler` | string | `null` | Response handler name for proxy routes — see [Proxy Response Handlers](writing-handlers.md#proxy-response-handlers) |
| `handler` | string | `null` | Response handler name |
| `params` | object | `null` | Parameter injection (see [Parameter Injection](parameter-injection.md)) |
| `response` | object | `null` | Response configuration |
| `description` | string | `null` | Human-readable description |

## Proxy Config

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `service` | string | — | Backend service name from `services` |
| `path` | string | same as route | Target path with `{placeholder}` substitution |
| `skip_body` | bool | `false` | Don't forward the request body |
| `headers` | dict | `{}` | Extra headers for the proxied request |

## Response Config

- `response.wrap: "data"` — wraps the JSON response body in a key.

Examples:

```yaml
- path: /api/items
  proxy:
    service: inventory
    path: /items
  response:
    wrap: data
```

When the backend returns `{"items": [1, 2]}`, the gateway returns `{"data": {"items": [1, 2]}}`. This works for both proxy and handler routes.
