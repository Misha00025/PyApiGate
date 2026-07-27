# Getting Started

## Installation

```bash
pip install -r requirements.txt
```

## Configuration Setup

Copy the default route configuration:

```bash
cp configs_default/routes.yaml configs/routes.yaml
```

> If you run `python scripts/validate_config.py`, it will create the configs directory and copy defaults automatically.

## Configure routes.yaml

Open `configs/routes.yaml` and adjust:

- **`services`** — change `base_url` values to point to your backend services
- **`auth`** — set the authentication strategy (see [Authentication](authentication.md))
- **`routes`** — define your endpoints (see [Route Configuration](route-configuration.md))

## Run

```bash
python main.py
```

The server starts at `http://localhost:5000`.

## Verify

```bash
curl http://localhost:5000/hello
```

Expected response:

```json
{"status": "OK", "message": "Hello from PyApiGate!"}
```

## Project Structure

```
PyApiGate/
├── app/                # Engine (core gateway logic — don't modify)
│   ├── engine/         # Pipeline, proxy, models, registry
│   └── ...
├── configs_default/    # Default configs (copied on first run)
├── configs/            # Your configs (edit these)
├── handlers/           # Your access & response handlers
├── scripts/            # Utility scripts
├── docs/               # Documentation
├── main.py             # Dev server
└── asgi.py             # Production ASGI entrypoint
```
