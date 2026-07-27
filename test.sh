#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# Find preferred Python (check .venv first, then venv, then system)
PYTHON="python"
for p in .venv/bin/python venv/bin/python; do
    if [ -x "$p" ]; then
        PYTHON="$p"
        break
    fi
done

exec "$PYTHON" -m pytest tests/ -v "$@"
