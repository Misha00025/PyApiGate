# Application Configuration

## app.json

Application settings are stored in `configs/app.json`. It is created automatically by copying `configs_default/app.json` on the first run or when running `validate_config.py`.

```json
{
  "logging": {
    "level": "INFO",
    "file": null,
    "format": "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
  },
  "request_id": {
    "header": "X-Request-ID",
    "generate_if_missing": true
  }
}
```

### Fields

| Field | Description |
|-------|-------------|
| `logging.level` | Log level: `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `logging.file` | Path to log file (`null` = stdout only) |
| `logging.format` | Log message format |
| `request_id.header` | Header name for request ID |
| `request_id.generate_if_missing` | Auto-generate a UUID if the header is missing |

## routes.yaml

The main route configuration. See [Route Configuration](route-configuration.md).

## Environment Variables

All string values in `routes.yaml` support environment variable substitution:

- `${ENV_VAR}` — required variable; the application will fail to start if unset
- `${ENV_VAR:-default}` — optional variable with a default fallback

## validate_config.py

```bash
python scripts/validate_config.py
```

Checks that all required configuration files exist and are valid. Creates missing files from defaults automatically.

- Exit code **0** — configuration is valid
- Exit code **1** — validation failed
