#!/usr/bin/env bash
set -euo pipefail

export PYTHONPATH="src${PYTHONPATH:+:${PYTHONPATH}}"
export BIOPHARMA_AIRFLOW_MODE="${BIOPHARMA_AIRFLOW_MODE:-daily-cycle}"
if [[ "${BIOPHARMA_AIRFLOW_MODE}" == "scheduled-fetch" ]]; then
  DEFAULT_AIRFLOW_RUN_LOG="/opt/airflow/project/data/runs/airflow_fetch_runs.jsonl"
  DEFAULT_HOST_AIRFLOW_RUN_LOG="data/runs/airflow_fetch_runs.jsonl"
else
  DEFAULT_AIRFLOW_RUN_LOG="/opt/airflow/project/data/runs/airflow_daily_cycles.jsonl"
  DEFAULT_HOST_AIRFLOW_RUN_LOG="data/runs/airflow_daily_cycles.jsonl"
fi
export BIOPHARMA_AIRFLOW_SOURCE_STATE="${BIOPHARMA_AIRFLOW_SOURCE_STATE:-/opt/airflow/project/data/runs/airflow_source_state.json}"
export BIOPHARMA_AIRFLOW_RUN_LOG="${BIOPHARMA_AIRFLOW_RUN_LOG:-${DEFAULT_AIRFLOW_RUN_LOG}}"
export BIOPHARMA_AIRFLOW_REPORT_MD="${BIOPHARMA_AIRFLOW_REPORT_MD:-/opt/airflow/project/data/reports/airflow_latest_brief.md}"
export BIOPHARMA_AIRFLOW_REPORT_JSON="${BIOPHARMA_AIRFLOW_REPORT_JSON:-/opt/airflow/project/data/reports/airflow_latest_brief.json}"
export HOST_AIRFLOW_SOURCE_STATE="${HOST_AIRFLOW_SOURCE_STATE:-data/runs/airflow_source_state.json}"
export HOST_AIRFLOW_RUN_LOG="${HOST_AIRFLOW_RUN_LOG:-${DEFAULT_HOST_AIRFLOW_RUN_LOG}}"
export HOST_AIRFLOW_REPORT_MD="${HOST_AIRFLOW_REPORT_MD:-data/reports/airflow_latest_brief.md}"
export HOST_AIRFLOW_REPORT_JSON="${HOST_AIRFLOW_REPORT_JSON:-data/reports/airflow_latest_brief.json}"

rm -f data/runs/airflow_fetch_runs.jsonl data/runs/airflow_daily_cycles.jsonl \
  "${HOST_AIRFLOW_RUN_LOG}" "${HOST_AIRFLOW_SOURCE_STATE}" \
  "${HOST_AIRFLOW_REPORT_MD}" "${HOST_AIRFLOW_REPORT_JSON}"

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
import os
from pathlib import Path

mode = os.environ.get("BIOPHARMA_AIRFLOW_MODE", "daily-cycle")
path = Path(os.environ.get("HOST_AIRFLOW_RUN_LOG", "data/runs/airflow_daily_cycles.jsonl"))
state_path = Path(os.environ.get("HOST_AIRFLOW_SOURCE_STATE", "data/runs/airflow_source_state.json"))
report_md = Path(os.environ.get("HOST_AIRFLOW_REPORT_MD", "data/reports/airflow_latest_brief.md"))
report_json = Path(os.environ.get("HOST_AIRFLOW_REPORT_JSON", "data/reports/airflow_latest_brief.json"))
if not path.exists() or not path.read_text(encoding="utf-8").strip():
    raise SystemExit("Airflow smoke did not write a run log")
if not state_path.exists() or not state_path.read_text(encoding="utf-8").strip():
    raise SystemExit("Airflow smoke did not write a source state file")
records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
latest = records[-1]
if latest.get("status") != "success":
    raise SystemExit(f"Expected latest Airflow run to succeed, got {latest.get('status')}")
result = latest.get("result") or {}
if mode == "daily-cycle":
    if not report_md.exists() or not report_md.read_text(encoding="utf-8").strip():
        raise SystemExit("Airflow smoke did not write a Markdown brief")
    if not report_json.exists() or not report_json.read_text(encoding="utf-8").strip():
        raise SystemExit("Airflow smoke did not write a JSON brief")
    fetch_rows = result.get("fetch", []) if isinstance(result, dict) else []
    brief = result.get("brief", {}) if isinstance(result, dict) else {}
else:
    fetch_rows = result if isinstance(result, list) else []
    brief = {}
selected = sum(int(item.get("selected") or 0) for item in fetch_rows if isinstance(item, dict))
analyzed = sum(int(item.get("analyzed") or 0) for item in fetch_rows if isinstance(item, dict))
skipped = sum(int(item.get("skipped_seen") or 0) for item in fetch_rows if isinstance(item, dict))
if selected < 1:
    raise SystemExit(f"Expected Airflow run to select at least one document, got {selected}")
if mode == "daily-cycle" and int(brief.get("document_count") or 0) < 1:
    raise SystemExit(f"Expected Airflow daily cycle to build a brief, got {brief}")
state = json.loads(state_path.read_text(encoding="utf-8"))
sources = state.get("sources", {}) if isinstance(state, dict) else {}
fda_state = sources.get("fda_press_releases", {}) if isinstance(sources, dict) else {}
if fda_state.get("last_status") != "success":
    raise SystemExit(f"Expected FDA source state success, got {fda_state.get('last_status')}")
if int(fda_state.get("last_selected") or 0) < 1:
    raise SystemExit(f"Expected FDA source state to record selected docs, got {fda_state}")
print(
    {
        "airflow_mode": mode,
        "airflow_run_log": str(path),
        "airflow_source_state": str(state_path),
        "airflow_report_md": str(report_md) if mode == "daily-cycle" else "",
        "airflow_report_json": str(report_json) if mode == "daily-cycle" else "",
        "bytes": path.stat().st_size,
        "run_status": latest.get("status"),
        "selected": selected,
        "analyzed": analyzed,
        "skipped_seen": skipped,
        "brief_document_count": int(brief.get("document_count") or 0),
        "source_state_seen": int(fda_state.get("seen_count") or 0),
    }
)
PY
