#!/usr/bin/env bash
# Open a psql shell against the local compose DB.
set -euo pipefail
docker compose exec -e PGPASSWORD="${POSTGRES_PASSWORD:-liwang}" db \
  psql -U liwang -d liwang "$@"
