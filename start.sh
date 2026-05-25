#!/usr/bin/env bash
set -o errexit

# Render injects $PORT. Daphne must bind to it.
# If PORT is not set, fallback to 8000 for local dev.
APP_PORT="${PORT:-8000}"

echo "Starting Daphne on 0.0.0.0:$APP_PORT"
daphne -b 0.0.0.0 -p "$APP_PORT" voip_backend.asgi:application
