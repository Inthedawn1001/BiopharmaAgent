#!/usr/bin/env bash
set -euo pipefail

export PYTHONPATH="src${PYTHONPATH:+:${PYTHONPATH}}"
export BIOPHARMA_POSTGRES_DSN="${BIOPHARMA_POSTGRES_DSN:-postgresql://biopharma:biopharma@127.0.0.1:55432/biopharma_agent}"
export BIOPHARMA_STORAGE_BACKEND="${BIOPHARMA_STORAGE_BACKEND:-postgres}"
export BIOPHARMA_RAW_ARCHIVE_BACKEND="${BIOPHARMA_RAW_ARCHIVE_BACKEND:-minio}"
export BIOPHARMA_RAW_ARCHIVE_S3_BUCKET="${BIOPHARMA_RAW_ARCHIVE_S3_BUCKET:-biopharma-raw}"
export BIOPHARMA_RAW_ARCHIVE_S3_PREFIX="${BIOPHARMA_RAW_ARCHIVE_S3_PREFIX:-raw}"
export BIOPHARMA_RAW_ARCHIVE_S3_ENDPOINT_URL="${BIOPHARMA_RAW_ARCHIVE_S3_ENDPOINT_URL:-http://127.0.0.1:9000}"
export BIOPHARMA_RAW_ARCHIVE_S3_REGION="${BIOPHARMA_RAW_ARCHIVE_S3_REGION:-us-east-1}"
export BIOPHARMA_RAW_ARCHIVE_S3_ACCESS_KEY_ID="${BIOPHARMA_RAW_ARCHIVE_S3_ACCESS_KEY_ID:-minioadmin}"
export BIOPHARMA_RAW_ARCHIVE_S3_SECRET_ACCESS_KEY="${BIOPHARMA_RAW_ARCHIVE_S3_SECRET_ACCESS_KEY:-minioadmin}"

docker compose up -d postgres minio minio-init

python3 - <<'PY'
import socket
import time

for host, port in [("127.0.0.1", 55432), ("127.0.0.1", 9000)]:
    deadline = time.time() + 60
    while True:
        try:
            with socket.create_connection((host, port), timeout=2):
                break
        except OSError:
            if time.time() > deadline:
                raise
            time.sleep(2)
PY

bash scripts/run_postgres_integration.sh
bash scripts/run_minio_smoke.sh

python3 -m biopharma_agent.cli scheduled-fetch \
  --sources fda_press_releases \
  --limit 1 \
  --max-runs 1 \
  --fetch-details \
  --clean-html-details \
  --run-log data/runs/full_stack_fetch_runs.jsonl \
  --no-graph

python3 - <<'PY'
from biopharma_agent.storage.postgres import PostgresAnalysisRepository
from biopharma_agent.storage.repository import DocumentFilters
import os

repo = PostgresAnalysisRepository(os.environ["BIOPHARMA_POSTGRES_DSN"])
docs = repo.list_documents(DocumentFilters(source="fda_press_releases", limit=5))
print({"postgres_fda_documents": docs.count, "filtered_total": docs.filtered_total})
PY
