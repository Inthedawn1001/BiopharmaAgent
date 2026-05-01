# Airflow Wrapper

This folder contains an optional Airflow DAG wrapper for recurring feed
collection. The core scheduler is still the lightweight `scheduled-fetch`
command, so Airflow only needs to invoke the same CLI entrypoint.

## Local CLI Equivalent

```bash
PYTHONPATH=src python3 -m biopharma_agent.cli scheduled-fetch \
  --sources fda_press_releases biopharma_dive_news \
  --limit 2 \
  --max-runs 1 \
  --run-log data/runs/fetch_runs.jsonl
```

Add `--analyze` after configuring an LLM provider.

## Airflow Deployment

1. Install the package into the Airflow worker image or environment.
2. Mount `infra/airflow/dags/biopharma_fetch_sources.py` into the Airflow DAGs folder.
3. Set environment variables as needed:

```bash
BIOPHARMA_AIRFLOW_SOURCES="fda_press_releases biopharma_dive_news"
BIOPHARMA_AIRFLOW_LIMIT=2
BIOPHARMA_AIRFLOW_ANALYZE=0
BIOPHARMA_AIRFLOW_SCHEDULE="0 * * * *"
BIOPHARMA_AIRFLOW_RUN_LOG=data/runs/airflow_fetch_runs.jsonl
BIOPHARMA_AIRFLOW_PYTHON=python3
```

The DAG intentionally shells out to the CLI. That keeps Airflow thin and avoids
duplicating source selection, storage, graph, and LLM configuration logic.

## Docker Smoke

The repo-level Compose file includes an optional `airflow` profile that runs the
DAG once with `airflow dags test` and writes a local run log:

```bash
scripts/run_airflow_smoke.sh
```

By default this smoke uses `fda_press_releases`, `limit=1`, and `analyze=0` so it
does not require an LLM key. Set `BIOPHARMA_AIRFLOW_ANALYZE=1` and normal
`BIOPHARMA_LLM_*` variables if you want the Airflow run to perform real LLM
analysis. The smoke script validates that the latest run log entry succeeded and
selected at least one source document. Set `PYTHON=/path/to/python` when the
host-side post-check should use a specific virtualenv.
