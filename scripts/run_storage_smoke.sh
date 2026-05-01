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
    deadline = time.time() + 90
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

"${PYTHON}" - <<'PY'
import os
from urllib.parse import urlparse

import boto3

from biopharma_agent.config import RawArchiveSettings
from biopharma_agent.storage.postgres import PostgresAnalysisRepository
from biopharma_agent.storage.repository import DocumentFilters

repo = PostgresAnalysisRepository(os.environ["BIOPHARMA_POSTGRES_DSN"])
docs = repo.list_documents(DocumentFilters(source="postgres_smoke", limit=5))
if docs.filtered_total < 1:
    raise SystemExit("Expected at least one PostgreSQL smoke document")

settings = RawArchiveSettings.from_env()
client = boto3.client(
    "s3",
    endpoint_url=settings.s3_endpoint_url or None,
    aws_access_key_id=settings.s3_access_key_id or None,
    aws_secret_access_key=settings.s3_secret_access_key or None,
    region_name=settings.s3_region or None,
)
raw_uri = f"s3://{settings.s3_bucket}/{settings.s3_prefix.strip('/')}/s3_smoke/s3-smoke-doc/raw.txt"
parsed = urlparse(raw_uri)
client.head_object(Bucket=parsed.netloc, Key=parsed.path.lstrip("/"))

print(
    {
        "postgres_smoke_documents": docs.filtered_total,
        "minio_raw_uri": raw_uri,
        "storage_smoke": "ok",
    }
)
PY
