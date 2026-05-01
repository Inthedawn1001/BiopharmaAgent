#!/usr/bin/env bash
set -euo pipefail

export PYTHONPATH="src${PYTHONPATH:+:${PYTHONPATH}}"

if [[ -z "${PYTHON:-}" ]]; then
  if [[ -n "${VIRTUAL_ENV:-}" && -x "${VIRTUAL_ENV}/bin/python" ]]; then
    PYTHON="${VIRTUAL_ENV}/bin/python"
  elif [[ -x ".venv/bin/python" ]]; then
    PYTHON=".venv/bin/python"
  else
    PYTHON="python3"
  fi
fi

docker compose --profile airflow up --abort-on-container-exit --exit-code-from airflow airflow

"${PYTHON}" - <<'PY'
import json
from pathlib import Path

path = Path("data/runs/airflow_fetch_runs.jsonl")
if not path.exists() or not path.read_text(encoding="utf-8").strip():
    raise SystemExit("Airflow smoke did not write a run log")
records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
latest = records[-1]
if latest.get("status") != "success":
    raise SystemExit(f"Expected latest Airflow run to succeed, got {latest.get('status')}")
result = latest.get("result") or []
selected = sum(int(item.get("selected") or 0) for item in result if isinstance(item, dict))
if selected < 1:
    raise SystemExit(f"Expected Airflow run to select at least one document, got {selected}")
print(
    {
        "airflow_run_log": str(path),
        "bytes": path.stat().st_size,
        "run_status": latest.get("status"),
        "selected": selected,
    }
)
PY
