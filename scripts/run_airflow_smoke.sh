#!/usr/bin/env bash
set -euo pipefail

export PYTHONPATH="src${PYTHONPATH:+:${PYTHONPATH}}"

docker compose --profile airflow up --abort-on-container-exit --exit-code-from airflow airflow

python3 - <<'PY'
from pathlib import Path

path = Path("data/runs/airflow_fetch_runs.jsonl")
if not path.exists() or not path.read_text(encoding="utf-8").strip():
    raise SystemExit("Airflow smoke did not write a run log")
print({"airflow_run_log": str(path), "bytes": path.stat().st_size})
PY
