#!/usr/bin/env bash
set -euo pipefail

export PYTHONPATH="src${PYTHONPATH:+:${PYTHONPATH}}"
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

"${PYTHON}" scripts/s3_archive_smoke.py
