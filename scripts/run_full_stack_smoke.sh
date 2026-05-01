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
export BIOPHARMA_LLM_PROVIDER="${BIOPHARMA_LLM_PROVIDER:-smoke}"
export BIOPHARMA_LLM_MODEL="${BIOPHARMA_LLM_MODEL:-smoke-model}"

if [[ -z "${PYTHON:-}" ]]; then
  if [[ -n "${VIRTUAL_ENV:-}" && -x "${VIRTUAL_ENV}/bin/python" ]]; then
    PYTHON="${VIRTUAL_ENV}/bin/python"
  elif [[ -x ".venv/bin/python" ]]; then
    PYTHON=".venv/bin/python"
  else
    PYTHON="python3"
  fi
fi

docker compose up -d postgres minio minio-init

"${PYTHON}" - <<'PY'
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

"${PYTHON}" -m biopharma_agent.cli scheduled-fetch \
  --sources fda_press_releases \
  --limit 1 \
  --max-runs 1 \
  --analyze \
  --fetch-details \
  --clean-html-details \
  --run-log data/runs/full_stack_fetch_runs.jsonl \
  --no-graph

"${PYTHON}" - <<'PY'
import json
from pathlib import Path
from urllib.parse import urlparse

import boto3

from biopharma_agent.config import RawArchiveSettings
from biopharma_agent.storage.postgres import PostgresAnalysisRepository
from biopharma_agent.storage.repository import DocumentFilters
import os

repo = PostgresAnalysisRepository(os.environ["BIOPHARMA_POSTGRES_DSN"])
docs = repo.list_documents(DocumentFilters(source="fda_press_releases", limit=5))
if docs.filtered_total < 1:
    raise SystemExit("Expected at least one analyzed FDA document in PostgreSQL")
raw_uri = docs.items[0].get("record", {}).get("document", {}).get("raw", {}).get("raw_uri", "")
if not raw_uri:
    raise SystemExit("Expected analyzed FDA document to include raw_uri")

settings = RawArchiveSettings.from_env()
parsed = urlparse(raw_uri)
client = boto3.client(
    "s3",
    endpoint_url=settings.s3_endpoint_url or None,
    aws_access_key_id=settings.s3_access_key_id or None,
    aws_secret_access_key=settings.s3_secret_access_key or None,
    region_name=settings.s3_region or None,
)
client.head_object(Bucket=parsed.netloc, Key=parsed.path.lstrip("/"))

run_log = Path("data/runs/full_stack_fetch_runs.jsonl")
records = [json.loads(line) for line in run_log.read_text(encoding="utf-8").splitlines() if line.strip()]
latest = records[-1]
if latest.get("status") != "success":
    raise SystemExit(f"Expected latest full-stack run to succeed, got {latest.get('status')}")
result = latest.get("result") or []
selected = sum(int(item.get("selected") or 0) for item in result if isinstance(item, dict))
analyzed = sum(int(item.get("analyzed") or 0) for item in result if isinstance(item, dict))
if selected < 1 or analyzed < 1:
    raise SystemExit(f"Expected selected and analyzed documents, got selected={selected}, analyzed={analyzed}")

print(
    {
        "postgres_fda_documents": docs.count,
        "filtered_total": docs.filtered_total,
        "raw_uri": raw_uri,
        "run_status": latest.get("status"),
        "selected": selected,
        "analyzed": analyzed,
    }
)
PY
