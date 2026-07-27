# Deployment

## Local Development

```bash
pip install -r requirements.txt
cp configs_default/routes.yaml configs/routes.yaml
python main.py
```

The dev server starts at `http://localhost:5000`.

## ASGI (Production)

```bash
CONFIG_PATH=/app/configs/routes.yaml uvicorn asgi:app --host 0.0.0.0 --port 5000
```

`asgi.py` reads the `CONFIG_PATH` environment variable to locate the route configuration.

## Docker

```bash
docker build -t pyapi-gate .
docker run -p 5000:5000 \
  -v ./configs:/app/configs:ro \
  -e CONFIG_PATH=/app/configs/routes.yaml \
  pyapi-gate
```

## Docker Compose

```bash
docker compose up -d
```

The included `docker-compose.yml` uses `ghcr.io/misha00025/pyapi-gate:latest` and mounts `./configs` as read-only.

## CI/CD

- **CI:** GitHub Actions runs on Python 3.12, 3.13, and 3.14 with pytest and coverage
- **CD:** Publishing to `ghcr.io` on tags matching `v*`

## Dependencies

- fastapi
- uvicorn
- requests
- PyJWT
- PyYAML
- httpx
- cryptography

## Port

The service uses port **5000** in all configurations: `main.py`, `Dockerfile`, and `docker-compose.yml`.
