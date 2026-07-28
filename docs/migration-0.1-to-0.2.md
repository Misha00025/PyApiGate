# Migration Guide: 0.1.x → 0.2.0

## Breaking Changes

### 1. `ctx.state["body"]` removed

In 0.1.x, the request body was pre-read and stored in `ctx.state["body"]` as a string or bytes.
In 0.2.0, use `ctx.request.body` (bytes, after `load_body()`) or `ctx.request.json` (parsed dict).

**Before (0.1.x):**
```python
body = ctx.state["body"]
```

**After (0.2.0):**
```python
await ctx.request.load_body()  # called automatically by pipeline
body_bytes = ctx.request.body   # raw bytes
body_json = ctx.request.json    # parsed dict (or None)
```

### 2. `ctx.request.json()` → `ctx.request.json` (property)

In 0.1.x, `ctx.request.json()` was an async method on FastAPI's Request.
In 0.2.0, `ctx.request.json` is a **synchronous property** on GatewayRequest that returns the cached parsed JSON (or None).

**Before (0.1.x):**
```python
data = await ctx.request.json()
```

**After (0.2.0):**
```python
data = ctx.request.json  # synchronous, may be None
```

### 3. `params.query: "*"` no longer adds `userId`

In 0.1.x, `params.query: "*"` forwarded all incoming query parameters **plus** automatically injected `userId` from JWT.
In 0.2.0, `"*"` forwards all parameters as-is — nothing is added automatically.

**Before (0.1.x):**
```yaml
params:
  query: "*"
# Result: ?a=1&b=2&userId=user123
```

**After (0.2.0):**
```yaml
params:
  query: "*"
# Result: ?a=1&b=2  — no userId injected

# To add userId explicitly:
params:
  query:
    - "*"
    - userId: "{jwt.sub}"
```

### 4. `get_user_id()` removed

The function `app.security.get_user_id()` has been removed. Use the source expression system instead:

```python
# Instead of:
from app.security import get_user_id
user_id = get_user_id(ctx.jwt)

# Use:
from app.engine.proxy import _resolve_source
user_id = _resolve_source("{jwt.userId}", ctx)
# or directly:
user_id = ctx.jwt.get("userId") or ctx.jwt.get("sub") if ctx.jwt else None
```

### 5. `app/security.py` deleted

This module no longer exists. See point 4 for replacement.

## New Features in 0.2.0

- **GatewayRequest** — cached body/json wrapper (solves single-consumption stream issue)
- **Config system** — `configs/app.json` with defaults from `configs_default/`
- **Structured logging** — request IDs, timing, per-request log lines
- **Error handling** — try/except wrappers around handlers with proper error logging
- **`X-Deny-Reason` header** — identifies which access handler denied a request
- **Healthcheck endpoint** — `GET /health` returns `{"status": "ok"}`
- **List form for query params** — `["*", {"key": "{jwt.sub}"}]` syntax
