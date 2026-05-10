#!/usr/bin/env bash
# Dev server. Requires: uv (https://docs.astral.sh/uv/) and a running Postgres
# (start it via `docker compose up -d db` first).
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  echo "warn: no .env found — copy .env.example and fill in DASHSCOPE_API_KEY" >&2
fi

uv run --with-editable . uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
