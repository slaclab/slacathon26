#!/bin/bash
#
# SLACATHON 2026 backend launcher
#
# All tasks in src/slacathon/tasks/ are served at once (GET /tasks lists them).
#

set -e

# Determine root from script location (supports invocation from anywhere)
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Load .env from root (after cd so relative .env works)
if [ -f .env ]; then
    # shellcheck disable=SC1091
    set -a
    . ./.env
    set +a
    echo "Loaded environment from .env"
fi

# See src/slacathon/tasks/ and GET /tasks/{task_id} for schema.

# Activate virtualenv and start the server (relocatable)
source "$ROOT/venv/bin/activate"
export PYTHONPATH="$ROOT/src"

# Gunicorn with explicit logging so we can debug 500s / worker crashes
exec gunicorn \
    -k uvicorn.workers.UvicornWorker \
    -w 1 \
    --timeout 300 \
    --bind 127.0.0.1:8888 \
    --access-logfile gunicorn-access.log \
    --error-logfile gunicorn-error.log \
    --log-level info \
    slacathon.main:app
