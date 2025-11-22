#!/usr/bin/env bash
set -euo pipefail

HOST=${SERVICE_HOST:-0.0.0.0}
PORT=${SERVICE_PORT:-8000}

exec uvicorn src.main:app --host "$HOST" --port "$PORT"
