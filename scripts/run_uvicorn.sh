#!/usr/bin/env bash
set -euo pipefail
shopt -s extglob

HOST=${SERVICE_HOST:-0.0.0.0}
PORT=${SERVICE_PORT:-8000}
LOG_LEVEL=${UVICORN_LOG_LEVEL:-info}

LOG_LEVEL=${LOG_LEVEL,,}
LOG_LEVEL=${LOG_LEVEL##+([[:space:]])}
LOG_LEVEL=${LOG_LEVEL%%+([[:space:]])}
if [[ -z "$LOG_LEVEL" ]]; then
  LOG_LEVEL=info
fi

exec uvicorn src.main:app --host "$HOST" --port "$PORT" --log-level "$LOG_LEVEL"
