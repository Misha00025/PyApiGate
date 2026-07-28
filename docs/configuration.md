# Application Configuration

## app.json

Application settings are stored in `configs/app.json`. It is created automatically by copying `configs_default/app.json` on the first run or when running `validate_config.py`.

```json
{
  "logging": {
    "level": "INFO",
    "file": null,
    "format": "%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
    "rotation": {
      "type": "timed",
      "when": "midnight",
      "interval": 1,
      "backup_count": 7
    }
  },
  "routes": {
    "files": ["routes.yaml"]
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
| `logging.rotation` | Log rotation settings (`null` = no rotation) |
| `routes.files` | List of YAML route configuration files to load. Each file is self-contained (base_path, auth, services, routes). Paths are relative to the app.json directory. If omitted, defaults to `["routes.yaml"]`. |

#### `logging.rotation` (optional)

Конфигурация ротации логов. Если `null` или отсутствует — используется обычный `FileHandler` без ротации.

| Поле | Тип | Описание |
|------|-----|----------|
| `type` | `"size"` или `"timed"` | Тип ротации |
| `max_bytes` | int | Максимальный размер файла в байтах (только для `type: "size"`). По умолчанию 10485760 (10 MB) |
| `when` | string | Интервал ротации (только для `type: "timed"`). Значения: `"midnight"`, `"S"` (секунды), `"M"` (минуты), `"H"` (часы), `"D"` (дни), `"W0"`-`"W6"` (день недели). По умолчанию `"midnight"` |
| `interval` | int | Интервал в единицах `when` (только для `type: "timed"`). По умолчанию 1 |
| `backup_count` | int | Количество хранимых файлов. По умолчанию 7 |

Примеры:

```json
{
  "logging": {
    "file": "logs/gateway.log",
    "rotation": {
      "type": "size",
      "max_bytes": 10485760,
      "backup_count": 7
    }
  }
}
```

```json
{
  "logging": {
    "file": "logs/gateway.log",
    "rotation": {
      "type": "timed",
      "when": "midnight",
      "interval": 1,
      "backup_count": 30
    }
  }
}
```

**Важно:** `logging.file` должен быть указан, чтобы ротация работала.
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
