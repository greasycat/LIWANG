#!/usr/bin/env bash
# Apply pending Alembic migrations against the configured DATABASE_URL.
set -euo pipefail
cd "$(dirname "$0")/.."
uv run --with-editable . alembic upgrade head
