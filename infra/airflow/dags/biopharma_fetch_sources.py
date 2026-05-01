"""Airflow DAG wrapper for recurring Biopharma Agent feed collection.

Copy or mount this file into an Airflow DAGs folder after installing the
biopharma-agent package in the Airflow worker environment.
"""

from __future__ import annotations

import os
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from airflow import DAG
from airflow.operators.python import PythonOperator


DEFAULT_ARGS = {
    "owner": "biopharma-agent",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


def run_fetch_sources() -> dict[str, object]:
    sources = os.getenv("BIOPHARMA_AIRFLOW_SOURCES", "").split()
    profile = os.getenv("BIOPHARMA_AIRFLOW_PROFILE", "").strip()
    limit = os.getenv("BIOPHARMA_AIRFLOW_LIMIT", "3")
    run_log = os.getenv("BIOPHARMA_AIRFLOW_RUN_LOG", "data/runs/airflow_fetch_runs.jsonl")
    source_state = os.getenv("BIOPHARMA_AIRFLOW_SOURCE_STATE", "data/runs/airflow_source_state.json")
    python_executable = os.getenv("BIOPHARMA_AIRFLOW_PYTHON", "python3")
    command = [
        python_executable,
        "-m",
        "biopharma_agent.cli",
        "scheduled-fetch",
        "--max-runs",
        "1",
        "--interval-seconds",
        "3600",
        "--limit",
        limit,
        "--run-log",
        run_log,
        "--state-path",
        source_state,
    ]
    if os.getenv("BIOPHARMA_AIRFLOW_ANALYZE", "0") == "1":
        command.append("--analyze")
    if os.getenv("BIOPHARMA_AIRFLOW_INCREMENTAL", "0") == "1":
        command.append("--incremental")
    if os.getenv("BIOPHARMA_AIRFLOW_FETCH_DETAILS", "0") == "1":
        command.append("--fetch-details")
    if os.getenv("BIOPHARMA_AIRFLOW_CLEAN_HTML_DETAILS", "0") == "1":
        command.append("--clean-html-details")
    if sources:
        command.append("--sources")
        command.extend(sources)
    elif profile:
        command.extend(["--profile", profile])
    subprocess.run(command, check=True)
    return _airflow_summary(run_log=run_log, source_state=source_state)


def _airflow_summary(*, run_log: str, source_state: str) -> dict[str, object]:
    latest = _latest_jsonl_record(Path(run_log))
    result = latest.get("result") if isinstance(latest, dict) else []
    rows = [item for item in result if isinstance(item, dict)] if isinstance(result, list) else []
    state_rows = _source_state_rows(Path(source_state))
    return {
        "run_log": run_log,
        "source_state": source_state,
        "status": latest.get("status", ""),
        "sources": latest.get("metadata", {}).get("sources", []) if isinstance(latest.get("metadata"), dict) else [],
        "selected": sum(int(item.get("selected") or 0) for item in rows),
        "analyzed": sum(int(item.get("analyzed") or 0) for item in rows),
        "skipped_seen": sum(int(item.get("skipped_seen") or 0) for item in rows),
        "source_state_rows": len(state_rows),
        "source_state_seen": sum(int(item.get("seen_count") or 0) for item in state_rows),
        "latest_completed_at": latest.get("completed_at", ""),
    }


def _latest_jsonl_record(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return records[-1] if records and isinstance(records[-1], dict) else {}


def _source_state_rows(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    decoded = json.loads(path.read_text(encoding="utf-8") or "{}")
    sources = decoded.get("sources", {}) if isinstance(decoded, dict) else {}
    if not isinstance(sources, dict):
        return []
    return [value for value in sources.values() if isinstance(value, dict)]


with DAG(
    dag_id="biopharma_fetch_sources",
    default_args=DEFAULT_ARGS,
    description="Fetch configured biopharma intelligence sources.",
    schedule=os.getenv("BIOPHARMA_AIRFLOW_SCHEDULE", "0 * * * *"),
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["biopharma-agent", "collection"],
) as dag:
    PythonOperator(
        task_id="fetch_sources",
        python_callable=run_fetch_sources,
    )
