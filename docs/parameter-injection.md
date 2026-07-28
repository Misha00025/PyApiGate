# Parameter Injection

Parameters from JWT payload, URL path, and query parameters can be injected into proxied requests.

## Source Expressions

| Expression | Source |
|------------|--------|
| `{jwt.field}` | Value from JWT payload. `{jwt.userId}` searches for `userId`, falls back to `sub` |
| `{path.field}` | Value from `path_params` |
| `{query.field}` | Value from the incoming request's query parameters |
| `"literal"` | Static string passed as-is |

## params.query

Forward query parameters to the backend.

**Wildcard — forward all incoming query parameters as-is:**

```yaml
params:
  query: "*"
```

**Wildcard with additional mappings — forward all + add/override fields:**

```yaml
params:
  query:
    - "*"
    - userId: "{jwt.sub}"
```

When the incoming request has `?foo=bar`, the backend receives `?foo=bar&userId=<sub_value>`.

**Explicit mapping:**

```yaml
params:
  query:
    dest: "{jwt.sub}"
```

**Mixed mode — explicit fields plus all remaining parameters:**

```yaml
params:
  query:
    userId: "{jwt.sub}"
    "*": "*"
```

## params.body

Inject values into the JSON request body sent to the backend.

Body injection merges the specified fields into the original JSON body. Original fields are preserved — only the keys listed in `body:` are added or overridden.

```yaml
params:
  body:
    ownerId: "{jwt.userId}"
    groupId: "{path.group_id}"
```

## proxy.headers

Set additional headers on the proxied request. Values support the same source expressions as query and body parameters.

```yaml
proxy:
  headers:
    Authorization: "Bearer static-token"
    X-User: "{jwt.sub}"
    X-Group: "{path.group_id}"
```

> **Note:** Parameter injection (body and query) only works with JSON requests. For non-JSON body types (multipart/form-data, application/octet-stream, text/plain, etc.), the body is forwarded as-is without injection.
