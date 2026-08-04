#!/usr/bin/env bash
set -euo pipefail

records="${1:-100000}"
run_stamp="$(date -u +%Y%m%dT%H%M%SZ)"
result_dir="artifacts/performance/${run_stamp}"
mkdir -p "$result_dir"

docker compose --profile tools run --rm pipeline generate-demo data/benchmark.parquet \
  --format parquet --records "$records" --invalid-rate 0.02 --duplicate-rate 0.01
docker compose --profile tools run --rm pipeline run data/benchmark.parquet --incremental \
  | tee "$result_dir/command-output.json"
docker compose exec -T database psql -U "${POSTGRES_USER:-pipeline}" \
  -d "${POSTGRES_DB:-support_quality}" -Atc \
  "SELECT json_build_object('tickets', count(*)) FROM tickets;" \
  > "$result_dir/database-count.json"
printf '{"records_requested":%s,"measured_at":"%s"}\n' "$records" "$run_stamp" \
  > "$result_dir/benchmark-metadata.json"
echo "Benchmark artifacts: $result_dir"
