#!/usr/bin/env bash
# Run FastAPI + Next.js together for local dev. Requires:
#   - uv (https://docs.astral.sh/uv/) and a running Postgres
#     (start via `docker compose up -d db`)
#   - node + npm; web/ deps installed (`cd web && npm install`)
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ ! -f .env ]]; then
  echo "warn: no .env found — copy .env.example and fill in DASHSCOPE_API_KEY" >&2
fi

API_PORT="${LIWANG_API_PORT:-8000}"
WEB_PORT="${LIWANG_WEB_PORT:-3000}"

cleanup() { jobs -p | xargs -r kill 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "→ starting FastAPI on :${API_PORT}"
uv run --with-editable . uvicorn app.main:app --reload --host 0.0.0.0 --port "${API_PORT}" &

echo "→ starting Next.js on :${WEB_PORT}"
( cd web && LIWANG_API_URL="http://127.0.0.1:${API_PORT}" npm run dev -- -p "${WEB_PORT}" ) &

wait
