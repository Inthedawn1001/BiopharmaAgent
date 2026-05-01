#!/usr/bin/env bash
set -euo pipefail

export PYTHONPATH="src${PYTHONPATH:+:${PYTHONPATH}}"
export BIOPHARMA_AIRFLOW_SOURCE_STATE="${BIOPHARMA_AIRFLOW_SOURCE_STATE:-/opt/airflow/project/data/runs/airflow_source_state.json}"
export HOST_AIRFLOW_SOURCE_STATE="${HOST_AIRFLOW_SOURCE_STATE:-data/runs/airflow_source_state.json}"

rm -f data/runs/airflow_fetch_runs.jsonl "${HOST_AIRFLOW_SOURCE_STATE}"

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
state_path = Path("data/runs/airflow_source_state.json")
if not path.exists() or not path.read_text(encoding="utf-8").strip():
    raise SystemExit("Airflow smoke did not write a run log")
if not state_path.exists() or not state_path.read_text(encoding="utf-8").strip():
    raise SystemExit("Airflow smoke did not write a source state file")
records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
latest = records[-1]
if latest.get("status") != "success":
    raise SystemExit(f"Expected latest Airflow run to succeed, got {latest.get('status')}")
result = latest.get("result") or []
selected = sum(int(item.get("selected") or 0) for item in result if isinstance(item, dict))
analyzed = sum(int(item.get("analyzed") or 0) for item in result if isinstance(item, dict))
skipped = sum(int(item.get("skipped_seen") or 0) for item in result if isinstance(item, dict))
if selected < 1:
    raise SystemExit(f"Expected Airflow run to select at least one document, got {selected}")
state = json.loads(state_path.read_text(encoding="utf-8"))
sources = state.get("sources", {}) if isinstance(state, dict) else {}
fda_state = sources.get("fda_press_releases", {}) if isinstance(sources, dict) else {}
if fda_state.get("last_status") != "success":
    raise SystemExit(f"Expected FDA source state success, got {fda_state.get('last_status')}")
if int(fda_state.get("last_selected") or 0) < 1:
    raise SystemExit(f"Expected FDA source state to record selected docs, got {fda_state}")
print(
    {
        "airflow_run_log": str(path),
        "airflow_source_state": str(state_path),
        "bytes": path.stat().st_size,
        "run_status": latest.get("status"),
        "selected": selected,
        "analyzed": analyzed,
        "skipped_seen": skipped,
        "source_state_seen": int(fda_state.get("seen_count") or 0),
    }
)
PY
