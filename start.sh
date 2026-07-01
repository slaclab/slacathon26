#!/bin/bash
#
# SLACATHON 2026 backend launcher
#
# Security note: Set SLACATHON_API_KEYS in your environment before starting.
# Example:
#   export SLACATHON_API_KEYS="your_strong_key_1,your_strong_key_2"
# Or create a .env file (see .env.example) and it will be sourced automatically.
#
# To switch task logic:
#   export SLACATHON_ACTIVE_TASK=flat_beam   # or fel, mars, etc. (see tasks/ dir)
#

set -e

# Optionally load variables from .env in the same directory (if present)
if [ -f .env ]; then
    # shellcheck disable=SC1091
    set -a
    . ./.env
    set +a
    echo "Loaded environment from .env"
fi

# Switch tasks: export SLACATHON_ACTIVE_TASK=flat_beam  (or fel/mars)
# See tasks/ and GET /task for schema.

# Activate virtualenv and start the server
source /home/alex/backend/venv/bin/activate

# Gunicorn with explicit logging so we can debug 500s / worker crashes
exec gunicorn \
    -k uvicorn.workers.UvicornWorker \
    -w 1 \
    --timeout 300 \
    --bind 127.0.0.1:8888 \
    --access-logfile gunicorn-access.log \
    --error-logfile gunicorn-error.log \
    --log-level info \
    main:app

