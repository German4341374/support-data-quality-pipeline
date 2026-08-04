#!/usr/bin/env bash
set -euo pipefail

records="${1:-100}"
docker compose --profile tools run --rm pipeline migrate
docker compose --profile tools run --rm pipeline generate-demo data/smoke.jsonl \
  --format jsonl --records "$records" --invalid-rate 0 --duplicate-rate 0
docker compose --profile tools run --rm pipeline run data/smoke.jsonl --incremental
docker compose exec -T database psql -U "${POSTGRES_USER:-pipeline}" \
  -d "${POSTGRES_DB:-support_quality}" -Atc \
  "SELECT CASE WHEN count(*) = ${records} THEN 'ok' ELSE 'unexpected-count' END FROM tickets;" \
  | grep -Fx ok
