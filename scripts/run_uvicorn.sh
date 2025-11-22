#!/usr/bin/env bash
set -euo pipefail

HOST=${SERVICE_HOST:-0.0.0.0}
PORT=${SERVICE_PORT:-8000}
LOG_LEVEL=${UVICORN_LOG_LEVEL:-info}

exec uvicorn src.main:app --host "$HOST" --port "$PORT" --log-level "$LOG_LEVEL"
