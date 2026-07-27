# Request Pipeline

Every request passes through a 7-step pipeline in `execute_pipeline()`.

## Pipeline Steps

| # | Step | When | Action |
|---|------|------|--------|
| 1 | Request ID | always | Reads `X-Request-ID` from the header or generates a `uuid4()`. Stored in `ctx.state["request_id"]`. |
| 2 | Auth | `route.auth == "required"` | Calls the auth strategy. Returns a dict → `ctx.jwt`. Returns `None` → **401** Unauthorized. |
| 3 | Body Load | always | `await ctx.request.load_body()`. Caches the request body. |
| 4 | Access | `route.access` is set | Calls the access handler. `deny()` → **403** with `X-Deny-Reason` header. |
| 5 | Execute | `route.handler` is set | Calls the response handler. **If both `handler` and `proxy` are set, `handler` takes priority and `proxy` is ignored.** |
| 5a | Execute | only `proxy` is set | `execute_proxy()` — proxies the request to the backend service. |
| 6 | Wrap | `route.response.wrap` is set | Wraps the JSON response in `{"key": data}`. |
| 7 | Log | always | `INFO: GET /path -> 200 [req_id] (0.123s)` |

## X-Deny-Reason

When an access handler denies a request, the response includes the header `X-Deny-Reason: <access_handler_name>`. This helps identify which handler rejected the request.

## Error Handling

| Situation | Status Code |
|-----------|-------------|
| `auth=required` but no strategy configured | 501 |
| Auth strategy returned `None` | 401 |
| Unknown access handler | 501 |
| Access handler crashed | 403 |
| Access denied (`deny()`) | 403 |
| Unknown response handler | 501 |
| Unknown proxy service | 501 |
| HTTP error during proxy call | 502 |
| Handler crashed | 502 |
