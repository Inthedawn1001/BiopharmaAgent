# Production Runbook

This runbook covers the main operating loop for Biopharma Agent: collect source
items, analyze them with the configured model, update source health, generate a
brief, and validate the artifacts before an analyst uses them.

## Daily Intelligence Cycle

Run the complete local cycle:

```bash
PYTHONPATH=src python3 -m biopharma_agent.cli daily-cycle \
  --profile core_intelligence \
  --limit 1 \
  --incremental \
  --fetch-details \
  --clean-html-details \
  --report-md data/reports/latest_brief.md \
  --report-json data/reports/latest_brief.json
```

The command analyzes by default and therefore requires valid `BIOPHARMA_LLM_*`
environment variables. For keyless infrastructure tests, add `--no-analyze`.

## Readiness Gate

After each daily cycle, run the quality gate:

```bash
PYTHONPATH=src python3 -m biopharma_agent.cli quality-gate \
  --analysis-path data/processed/insights.jsonl \
  --brief-md data/reports/latest_brief.md \
  --source-state data/runs/source_state.json \
  --require-brief \
  --require-source-state
```

The gate exits with code `0` only when:

- the analysis repository has at least the configured minimum record count
- enough records contain summaries, events, risks, and usable body text
- the Markdown brief exists and includes the expected sections
- the source-state file exists and failed sources do not exceed the configured threshold

Use `--json` when an automation needs machine-readable output.

## Workbench Operation

Start the browser workbench:

```bash
PYTHONPATH=src python3 -m biopharma_agent.cli serve --host 127.0.0.1 --port 8765
```

The Run Monitor page can:

- select healthy sources
- retry failed sources
- trigger manual fetch jobs
- run the Daily Intelligence Cycle
- inspect source-state alerts and the source health report

The Market Intelligence panel can generate a fresh brief or load the latest
saved Markdown and JSON brief artifacts.

## Storage Profiles

Local JSONL mode is the default and is appropriate for development and small
single-operator runs.

PostgreSQL plus MinIO mode verifies production-shaped storage boundaries:

```bash
docker compose up -d postgres minio minio-init
export BIOPHARMA_STORAGE_BACKEND=postgres
export BIOPHARMA_POSTGRES_DSN="postgresql://biopharma:biopharma@127.0.0.1:55432/biopharma_agent"
export BIOPHARMA_RAW_ARCHIVE_BACKEND=minio
export BIOPHARMA_RAW_ARCHIVE_S3_BUCKET=biopharma-raw
export BIOPHARMA_RAW_ARCHIVE_S3_ENDPOINT_URL=http://127.0.0.1:9000
export BIOPHARMA_RAW_ARCHIVE_S3_ACCESS_KEY_ID=minioadmin
export BIOPHARMA_RAW_ARCHIVE_S3_SECRET_ACCESS_KEY=minioadmin
PYTHONPATH=src python3 -m biopharma_agent.cli migrate-postgres
```

Then run:

```bash
scripts/run_storage_smoke.sh
scripts/run_full_stack_smoke.sh
```

## Airflow Operation

The Airflow DAG delegates to the same CLI used locally. Recommended settings:

```bash
BIOPHARMA_AIRFLOW_MODE=daily-cycle
BIOPHARMA_AIRFLOW_PROFILE=core_intelligence
BIOPHARMA_AIRFLOW_LIMIT=1
BIOPHARMA_AIRFLOW_ANALYZE=1
BIOPHARMA_AIRFLOW_INCREMENTAL=1
BIOPHARMA_AIRFLOW_FETCH_DETAILS=1
BIOPHARMA_AIRFLOW_CLEAN_HTML_DETAILS=1
BIOPHARMA_AIRFLOW_RUN_LOG=data/runs/airflow_daily_cycles.jsonl
BIOPHARMA_AIRFLOW_SOURCE_STATE=data/runs/airflow_source_state.json
BIOPHARMA_AIRFLOW_REPORT_MD=data/reports/airflow_latest_brief.md
BIOPHARMA_AIRFLOW_REPORT_JSON=data/reports/airflow_latest_brief.json
BIOPHARMA_AIRFLOW_BRIEF_LIMIT=100
```

Run the local Docker smoke:

```bash
scripts/run_airflow_smoke.sh
```

## Failure Handling

If a source fails, inspect the source-state report:

```bash
PYTHONPATH=src python3 -m biopharma_agent.cli source-report
```

Common outcomes:

- missing LLM credentials: configure `BIOPHARMA_LLM_API_KEY`, model, and base URL
- blocked or changed source page: source state records the failure diagnosis and remediation hint
- repeated duplicates: run with `--incremental` and check `last_skipped_seen`
- storage connection failure: run `diagnose`, then rerun the storage smoke for the selected backend

Secrets must stay in environment variables or local secret stores. Do not commit
API keys, local host names, generated data artifacts, or operator-specific paths.
