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

## ResponseBuilder — Modifying Any Response (asynchronous)

`ctx.response` (a `ResponseBuilder`) is initialized at the start of every request pipeline and is available to **all** handlers — access handlers, response handlers, and proxy response handlers alike.

Any handler can accumulate modifications (headers, cookies, body transformations) via `ctx.response`. At the end of the pipeline, modifications are applied automatically.

For **proxy routes with `response_handler`**, the handler mutates `ctx.response` directly (no return value needed) and the pipeline calls `ctx.response.finalize()` to build the final response.

For **all other routes** (handler routes, plain proxy routes), modifications are applied via `ctx.response.apply_to()` after the execute step.

```python
from app.engine.registry import register_response_handler
from app.engine.context import RouteContext

# Example 1: Proxy route with response_handler
@register_response_handler("wrap_auth_response")
async def handle_wrap_auth(ctx: RouteContext):
    body = ctx.response.body  # available after proxy execution

    ctx.response.keep_fields(["access_token", "expires_in"])
    ctx.response.set_cookie(
        "refresh_token", body["refresh_token"],
        httponly=True, samesite="strict",
    )
    ctx.response.set_header("X-Trace-Id", body.get("trace_id", ""))
    # No return — pipeline calls ctx.response.finalize()

# Example 2: Access handler setting a header
@register_access_handler("audit")
def audit_handler(ctx: RouteContext):
    ctx.response.set_header("X-Audit-Log", ctx.jwt.get("sub", "?"))
    return ctx.allow()

# Example 3: Response handler adding a cookie
@register_response_handler("add_tracking")
async def add_tracking(ctx: RouteContext):
    ctx.response.set_cookie("visitor", str(uuid.uuid4()))
    return JSONResponse({"message": "ok"})  # return still works
```

### ResponseBuilder API

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

> **Note:** `ctx.response.body` is only available after a proxy request has been executed (i.e., in a proxy response handler). Calling it earlier raises `RuntimeError`.

> **Note:** If both `response_handler` and `response.wrap` are configured, `response.wrap` is applied **after** the handler, wrapping the modified response.

## RouteContext API

| Attribute | Type | Description |
|-----------|------|-------------|
| `ctx.request` | `GatewayRequest` | Wrapper around the FastAPI Request |
| `ctx.path_params` | `dict` | URL parameters (always a `dict`) |
| `ctx.jwt` | `dict` or `None` | Decoded JWT payload |
| `ctx.services` | `ServiceRegistry` | HTTP clients for backend services |
| `ctx.response` | `ResponseBuilder` | Builder for modifying pipeline responses. Available to all handlers. Always initialized at pipeline start. |
| `ctx.state` | `dict` | Mutable storage between pipeline stages |

## GatewayRequest API

- `ctx.request.method`, `headers`, `query_params`, `url` — proxies to the FastAPI Request
- `ctx.request.path_params` — copy of `request.path_params` (always a `dict`)
- `ctx.request.cookies` — `dict[str, str]`, parsed request cookies
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
