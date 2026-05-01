"""Airflow DAG wrapper for recurring Biopharma Agent feed collection.

Copy or mount this file into an Airflow DAGs folder after installing the
biopharma-agent package in the Airflow worker environment.
"""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator


DEFAULT_ARGS = {
    "owner": "biopharma-agent",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
}


def run_fetch_sources() -> None:
    sources = os.getenv("BIOPHARMA_AIRFLOW_SOURCES", "").split()
    limit = os.getenv("BIOPHARMA_AIRFLOW_LIMIT", "3")
    run_log = os.getenv("BIOPHARMA_AIRFLOW_RUN_LOG", "data/runs/airflow_fetch_runs.jsonl")
    command = [
        "python3",
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
    ]
    if os.getenv("BIOPHARMA_AIRFLOW_ANALYZE", "0") == "1":
        command.append("--analyze")
    if sources:
        command.append("--sources")
        command.extend(sources)
    subprocess.run(command, check=True)


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
