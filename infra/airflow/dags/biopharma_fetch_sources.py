"""Airflow DAG wrapper for recurring Biopharma Agent intelligence jobs.

Copy or mount this file into an Airflow DAGs folder after installing the
biopharma-agent package in the Airflow worker environment.
"""

from __future__ import annotations

import json
import os
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
    mode = _airflow_mode()
    sources = os.getenv("BIOPHARMA_AIRFLOW_SOURCES", "").split()
    profile = os.getenv("BIOPHARMA_AIRFLOW_PROFILE", "").strip()
    limit = os.getenv("BIOPHARMA_AIRFLOW_LIMIT", "3")
    run_log = os.getenv("BIOPHARMA_AIRFLOW_RUN_LOG", _default_run_log(mode))
    source_state = os.getenv("BIOPHARMA_AIRFLOW_SOURCE_STATE", "data/runs/airflow_source_state.json")
    python_executable = os.getenv("BIOPHARMA_AIRFLOW_PYTHON", "python3")
    if mode == "daily-cycle":
        command = _daily_cycle_command(
            python_executable=python_executable,
            sources=sources,
            profile=profile,
            limit=limit,
            run_log=run_log,
            source_state=source_state,
        )
    else:
        command = _scheduled_fetch_command(
            python_executable=python_executable,
            sources=sources,
            profile=profile,
            limit=limit,
            run_log=run_log,
            source_state=source_state,
        )
    subprocess.run(command, check=True)
    return _airflow_summary(run_log=run_log, source_state=source_state)


def _scheduled_fetch_command(
    *,
    python_executable: str,
    sources: list[str],
    profile: str,
    limit: str,
    run_log: str,
    source_state: str,
) -> list[str]:
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
    _append_common_paths(command)
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
    return command


def _daily_cycle_command(
    *,
    python_executable: str,
    sources: list[str],
    profile: str,
    limit: str,
    run_log: str,
    source_state: str,
) -> list[str]:
    command = [
        python_executable,
        "-m",
        "biopharma_agent.cli",
        "daily-cycle",
        "--limit",
        limit,
        "--run-log",
        run_log,
        "--state-path",
        source_state,
        "--brief-limit",
        os.getenv("BIOPHARMA_AIRFLOW_BRIEF_LIMIT", "100"),
        "--report-md",
        os.getenv("BIOPHARMA_AIRFLOW_REPORT_MD", "data/reports/airflow_latest_brief.md"),
        "--report-json",
        os.getenv("BIOPHARMA_AIRFLOW_REPORT_JSON", "data/reports/airflow_latest_brief.json"),
        "--json",
    ]
    _append_common_paths(command)
    _append_optional_boolean(command, "BIOPHARMA_AIRFLOW_ANALYZE", "--analyze", "--no-analyze")
    _append_optional_boolean(command, "BIOPHARMA_AIRFLOW_INCREMENTAL", "--incremental", "--no-incremental")
    _append_optional_boolean(command, "BIOPHARMA_AIRFLOW_FETCH_DETAILS", "--fetch-details", "--no-fetch-details")
    _append_optional_boolean(
        command,
        "BIOPHARMA_AIRFLOW_CLEAN_HTML_DETAILS",
        "--clean-html-details",
        "--no-clean-html-details",
    )
    if sources:
        command.append("--sources")
        command.extend(sources)
    elif profile:
        command.extend(["--profile", profile])
    return command


def _airflow_summary(*, run_log: str, source_state: str) -> dict[str, object]:
    latest = _latest_jsonl_record(Path(run_log))
    result = latest.get("result") if isinstance(latest, dict) else []
    rows = _collection_rows(result)
    brief = result.get("brief", {}) if isinstance(result, dict) and isinstance(result.get("brief"), dict) else {}
    artifacts = brief.get("artifacts", {}) if isinstance(brief.get("artifacts"), dict) else {}
    state_rows = _source_state_rows(Path(source_state))
    return {
        "run_log": run_log,
        "source_state": source_state,
        "job_name": latest.get("job_name", ""),
        "status": latest.get("status", ""),
        "sources": _summary_sources(latest, result),
        "selected": sum(int(item.get("selected") or 0) for item in rows),
        "analyzed": sum(int(item.get("analyzed") or 0) for item in rows),
        "skipped_seen": sum(int(item.get("skipped_seen") or 0) for item in rows),
        "source_state_rows": len(state_rows),
        "source_state_seen": sum(int(item.get("seen_count") or 0) for item in state_rows),
        "brief_document_count": int(brief.get("document_count") or 0),
        "brief_summary": brief.get("summary", ""),
        "report_md": artifacts.get("markdown", ""),
        "report_json": artifacts.get("json", ""),
        "latest_completed_at": latest.get("completed_at", ""),
    }


def _airflow_mode() -> str:
    raw_mode = os.getenv("BIOPHARMA_AIRFLOW_MODE", "scheduled-fetch").strip().lower().replace("_", "-")
    aliases = {
        "fetch": "scheduled-fetch",
        "fetch-sources": "scheduled-fetch",
        "scheduled": "scheduled-fetch",
        "daily": "daily-cycle",
        "daily-cycle-once": "daily-cycle",
    }
    mode = aliases.get(raw_mode, raw_mode)
    if mode not in {"scheduled-fetch", "daily-cycle"}:
        raise ValueError(f"Unsupported BIOPHARMA_AIRFLOW_MODE: {raw_mode}")
    return mode


def _default_run_log(mode: str) -> str:
    if mode == "daily-cycle":
        return "data/runs/airflow_daily_cycles.jsonl"
    return "data/runs/airflow_fetch_runs.jsonl"


def _append_common_paths(command: list[str]) -> None:
    for env_name, flag in [
        ("BIOPHARMA_AIRFLOW_ARCHIVE_DIR", "--archive-dir"),
        ("BIOPHARMA_AIRFLOW_OUTPUT", "--output"),
        ("BIOPHARMA_AIRFLOW_GRAPH_DIR", "--graph-dir"),
        ("BIOPHARMA_AIRFLOW_DETAIL_DELAY_SECONDS", "--detail-delay-seconds"),
    ]:
        value = os.getenv(env_name, "").strip()
        if value:
            command.extend([flag, value])
    if _env_bool("BIOPHARMA_AIRFLOW_NO_GRAPH", default=False):
        command.append("--no-graph")


def _append_optional_boolean(command: list[str], env_name: str, enabled_flag: str, disabled_flag: str) -> None:
    raw_value = os.getenv(env_name)
    if raw_value is None or not raw_value.strip():
        return
    command.append(enabled_flag if _env_bool(env_name, default=False) else disabled_flag)


def _env_bool(env_name: str, *, default: bool) -> bool:
    raw_value = os.getenv(env_name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


def _collection_rows(result: object) -> list[dict[str, object]]:
    if isinstance(result, list):
        return [item for item in result if isinstance(item, dict)]
    if isinstance(result, dict):
        fetch = result.get("fetch")
        if isinstance(fetch, list):
            return [item for item in fetch if isinstance(item, dict)]
    return []


def _summary_sources(latest: dict[str, object], result: object) -> list[str]:
    metadata = latest.get("metadata", {})
    if isinstance(metadata, dict):
        for key in ["sources", "source_names"]:
            values = metadata.get(key)
            if isinstance(values, list):
                return [str(value) for value in values]
    if isinstance(result, dict) and isinstance(result.get("sources"), list):
        return [str(value) for value in result["sources"]]
    return []


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
