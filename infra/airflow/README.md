# Airflow Wrapper

This folder contains an optional Airflow DAG wrapper for recurring intelligence
jobs. Airflow stays thin: it shells out to the same CLI entrypoints used by
local development and the web workbench.

## Local CLI Equivalent

Daily intelligence cycle mode:

```bash
PYTHONPATH=src python3 -m biopharma_agent.cli daily-cycle \
  --profile core_intelligence \
  --limit 1 \
  --no-analyze \
  --fetch-details \
  --clean-html-details \
  --run-log data/runs/airflow_daily_cycles.jsonl \
  --report-md data/reports/airflow_latest_brief.md \
  --report-json data/reports/airflow_latest_brief.json
```

Legacy scheduled fetch mode:

```bash
PYTHONPATH=src python3 -m biopharma_agent.cli scheduled-fetch \
  --profile global_safety_alerts \
  --limit 2 \
  --max-runs 1 \
  --run-log data/runs/fetch_runs.jsonl
```

Use `--analyze` after configuring an LLM provider. Use `--sources` instead of
`--profile` when a DAG run needs an explicit source list. For production
schedules, prefer `daily-cycle` because it fetches sources, updates source
state, stores analysis, and generates brief artifacts in one repeatable run.

## Airflow Deployment

1. Install the package into the Airflow worker image or environment.
2. Mount `infra/airflow/dags/biopharma_fetch_sources.py` into the Airflow DAGs folder.
3. Set environment variables as needed:

```bash
BIOPHARMA_AIRFLOW_MODE=daily-cycle
BIOPHARMA_AIRFLOW_PROFILE=global_safety_alerts
BIOPHARMA_AIRFLOW_SOURCES=""
BIOPHARMA_AIRFLOW_LIMIT=2
BIOPHARMA_AIRFLOW_ANALYZE=0
BIOPHARMA_AIRFLOW_SCHEDULE="0 * * * *"
BIOPHARMA_AIRFLOW_RUN_LOG=data/runs/airflow_daily_cycles.jsonl
BIOPHARMA_AIRFLOW_SOURCE_STATE=data/runs/airflow_source_state.json
BIOPHARMA_AIRFLOW_INCREMENTAL=1
BIOPHARMA_AIRFLOW_FETCH_DETAILS=1
BIOPHARMA_AIRFLOW_CLEAN_HTML_DETAILS=1
BIOPHARMA_AIRFLOW_REPORT_MD=data/reports/airflow_latest_brief.md
BIOPHARMA_AIRFLOW_REPORT_JSON=data/reports/airflow_latest_brief.json
BIOPHARMA_AIRFLOW_BRIEF_LIMIT=100
BIOPHARMA_AIRFLOW_PYTHON=python3
```

`BIOPHARMA_AIRFLOW_MODE` accepts `daily-cycle` or `scheduled-fetch`. The default
is `scheduled-fetch` for backward compatibility, while the Compose smoke sets
`daily-cycle` to exercise the full intelligence loop. In `daily-cycle` mode,
unset boolean variables keep the CLI defaults; set them to `0` or `1` when the
DAG should force an option such as `--no-analyze` for keyless smoke tests.

`BIOPHARMA_AIRFLOW_PROFILE` accepts the same built-in profiles shown by
`list-source-profiles`, such as `core_intelligence`, `global_safety_alerts`,
`market_filings`, and `industry_news`. `BIOPHARMA_AIRFLOW_SOURCES` still accepts
a space-separated source list and takes precedence when set.

The DAG intentionally shells out to the CLI. That keeps Airflow thin and avoids
duplicating source selection, storage, graph, and LLM configuration logic.
The Python task returns a compact summary containing run status, selected and
analyzed counts, skipped seen-document counts, source-state row counts, and, in
daily-cycle mode, brief document counts plus report artifact paths so Airflow
task logs and XComs have operational context.

## Docker Smoke

The repo-level Compose file includes an optional `airflow` profile that runs the
DAG once with `airflow dags test` and writes a local run log:

```bash
scripts/run_airflow_smoke.sh
```

By default this smoke uses `daily-cycle`, `fda_press_releases`, `limit=1`, and
`analyze=0` so it does not require an LLM key. Set
`BIOPHARMA_AIRFLOW_ANALYZE=1` and normal `BIOPHARMA_LLM_*` variables if you want
the Airflow run to perform real LLM analysis. The smoke script validates that
the latest daily-cycle run log entry succeeded, selected at least one source
document, wrote source health, and generated Markdown/JSON brief artifacts. Set
`PYTHON=/path/to/python` when the host-side post-check should use a specific
virtualenv.
