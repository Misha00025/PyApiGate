# Writing Handlers

Handlers contain your business logic. They live in the `handlers/` directory and are auto-imported on startup.

The `handlers/` directory is `.gitignore`-d — your custom handlers stay out of the engine repository.

## Access Handlers (synchronous)

Access handlers perform permission checks. They must return `ctx.allow()` or `ctx.deny()`.

```python
from app.engine.registry import register_access_handler
from app.engine.context import RouteContext

@register_access_handler("admin_only")
def check_admin(ctx: RouteContext):
    if ctx.jwt and ctx.jwt.get("role") == "admin":
        return ctx.allow()
    return ctx.deny()
```

- If an access handler raises an exception, the response is **403**.
- On denial, the response header `X-Deny-Reason` is set to the handler name.

## Response Handlers (asynchronous)

Response handlers produce the response. They must return a Starlette `Response`.

> **Note:** If a route has both `handler` and `proxy` configured, the handler takes priority and `proxy` is ignored.

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

- Use `ctx.services.<name>.get/post/put/patch/delete(...)` to call backend services.
- Combine multiple service calls in a single handler (composite handler).

## Proxy Response Handlers (asynchronous)

Proxy response handlers modify the backend response **after** a proxy request. They are configured via `response_handler` on a proxy route.

The handler does **not** return a response — it mutates `ctx.response` (a `ProxyResponseBuilder`) which provides controlled methods for modifications.

```python
from app.engine.registry import register_response_handler
from app.engine.context import RouteContext

@register_response_handler("wrap_auth_response")
async def handle_wrap_auth(ctx: RouteContext):
    body = ctx.response.body

    # Keep only specific fields
    ctx.response.keep_fields(["access_token", "expires_in"])

    # Add Set-Cookie from a field in the backend response
    ctx.response.set_cookie(
        "refresh_token", body["refresh_token"],
        httponly=True, samesite="strict",
    )

    # Add a custom header
    ctx.response.set_header("X-Trace-Id", body.get("trace_id", ""))

    # Response is finalized automatically by the pipeline
```

### ProxyResponseBuilder API

| Method | Description |
|--------|-------------|
| `passthrough()` | Return the original backend response unchanged (ignores all modifications) |
| `set_status(code)` | Override the HTTP status code |
| `set_header(key, value)` | Set a response header |
| `remove_header(key)` | Remove a response header |
| `set_cookie(key, value, **kwargs)` | Add a `Set-Cookie` header. Supports `httponly`, `secure`, `samesite`, `max_age`, `path`, `domain`, `expires` |
| `set_body(data)` / `set_json(data)` | Replace the response body entirely (must be JSON-serializable) |
| `merge_body(data)` | Merge fields into the JSON response body |
| `keep_fields(fields)` | Keep only the specified top-level fields in the JSON body |
| `remove_fields(fields)` | Remove the specified top-level fields from the JSON body |

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `ctx.response.body` | `dict`, `list`, or `bytes` | Parsed JSON body of the backend response (lazy, cached) |
| `ctx.response.status_code` | `int` | Current status code (may have been modified) |

> **Note:** The handler must not call backend services directly — the proxy request has already been made. Use the builder methods only.

> **Note:** If both `response_handler` and `response.wrap` are configured, `response.wrap` is applied **after** the handler, wrapping the modified response.

## RouteContext API

| Attribute | Type | Description |
|-----------|------|-------------|
| `ctx.request` | `GatewayRequest` | Wrapper around the FastAPI Request |
| `ctx.path_params` | `dict` | URL parameters (always a `dict`) |
| `ctx.jwt` | `dict` or `None` | Decoded JWT payload |
| `ctx.services` | `ServiceRegistry` | HTTP clients for backend services |
| `ctx.response` | `ProxyResponseBuilder` or `None` | Builder for modifying proxy responses (only set during proxy response handler) |
| `ctx.state` | `dict` | Mutable storage between pipeline stages |

## GatewayRequest API

- `ctx.request.method`, `headers`, `query_params`, `url` — proxies to the FastAPI Request
- `ctx.request.path_params` — copy of `request.path_params` (always a `dict`)
- `ctx.request.body` — `Optional[bytes]`, synchronous access to the cached body
- `ctx.request.json` — `Optional[Any]`, synchronous access to the cached parsed JSON

> **Important:** The body is only available inside access/response handlers (after the pipeline calls `load_body()`). Do not attempt to read the body in an auth strategy.

## ServiceRegistry / ServiceClient

```python
resp = ctx.services.users.get("/profiles/123")
resp = ctx.services.users.post("/items", json={"name": "foo"})
resp = ctx.services.users.put("/items/1", json={"name": "bar"})
resp = ctx.services.users.patch("/items/1", json={"name": "baz"})
resp = ctx.services.users.delete("/items/1")
```

All methods accept the same keyword arguments as `requests.request`. They return a `requests.Response` object.

## Status Helpers

Import from `app.engine.status`:

| Helper | HTTP Status |
|--------|-------------|
| `ok(response=None)` | 200 |
| `created(response=None)` | 201 |
| `accepted(response=None)` | 202 |
| `bad_request(response=None)` | 400 |
| `unauthorized(response=None)` | 401 |
| `forbidden(response=None)` | 403 |
| `not_found(response=None)` | 404 |
| `conflict(response=None)` | 409 |
| `not_implemented(response=None)` | 501 |
| `bad_gateway(response=None)` | 502 |

- **Error (4xx, 5xx):** passing a string produces `{"error": "message"}`
- **Success (2xx):** passing a dict produces `{"status": "OK", ...response}`
