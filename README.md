# Biopharma Agent

Agent toolkit for biopharma industry and capital-market intelligence.

The current version includes the LLM abstraction layer, feed and source collection, local end-to-end analysis workflows, JSONL and optional PostgreSQL storage, local and S3-compatible raw-document archiving, JSONL or Neo4j knowledge graph writes, and a local web workbench. The architecture keeps deeper NLP/time-series modeling as clear extension points for Scrapy, Airflow, PostgreSQL, Neo4j, spaCy, LDA, ARIMA, and related components.

## Implemented

- Provider-neutral LLM request and response types
- OpenAI-compatible, Anthropic, Gemini, Ollama, and custom HTTP adapters
- Chat, embedding, and JSON-schema structured output abstractions
- Biopharma and capital-market document analysis pipeline
- Cross-document intelligence briefs with event mix, risk mix, key developments, and watchlists
- RSS/Atom, HTML listing, ASX announcement, and SEC EDGAR submissions collection with end-to-end storage
- Built-in source catalog for regulatory, industry news, and market news sources with category, priority, and rate-limit metadata
- HTML listing adapter for sources without stable RSS feeds
- JSONL local repository, idempotent writes, PostgreSQL schema/adapter, and SQL-level pagination
- Human feedback repository for JSONL and PostgreSQL backends
- Raw document archive for local filesystem and S3/MinIO-compatible object storage
- Lightweight scheduled fetch command with JSONL run logs
- Graph-shaped node and edge JSONL export plus optional Neo4j graph writes
- Local web workbench for document analysis, document inbox, run monitoring, manual fetch triggers, human review, time-series analysis, model settings, and runtime diagnostics
- Source health diagnosis with prioritized operational alerts for failed or disabled collectors
- Markdown source health reports for operations review from CLI or the workbench
- CLI commands for model checks, analysis, execution plans, migrations, and diagnostics
- Dependency-light unit tests
- GitHub Actions CI for unit-test regression checks

## Quick Start

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
PYTHONPATH=src python3 -m biopharma_agent.cli plan
PYTHONPATH=src python3 -m biopharma_agent.cli diagnose
```

Configure environment variables to call a real model:

```bash
export BIOPHARMA_LLM_PROVIDER=openai
export BIOPHARMA_LLM_BASE_URL=https://api.openai.com/v1
export BIOPHARMA_LLM_API_KEY=...
export BIOPHARMA_LLM_MODEL=gpt-4.1-mini

echo "A biotech company completed Series B financing and advanced a PD-1 phase 2 program." \
  | PYTHONPATH=src python3 -m biopharma_agent.cli analyze-text --stdin
```

Local Ollama example:

```bash
export BIOPHARMA_LLM_PROVIDER=ollama
export BIOPHARMA_LLM_BASE_URL=http://localhost:11434
export BIOPHARMA_LLM_MODEL=qwen2.5:7b

PYTHONPATH=src python3 -m biopharma_agent.cli llm-check
```

DeepSeek example:

```bash
export BIOPHARMA_LLM_PROVIDER=custom
export BIOPHARMA_LLM_BASE_URL=https://api.deepseek.com
export BIOPHARMA_LLM_MODEL=deepseek-chat
export BIOPHARMA_LLM_API_KEY=...

PYTHONPATH=src python3 -m biopharma_agent.cli llm-check
```

Infrastructure smoke tests can use the deterministic local provider without an external API key:

```bash
export BIOPHARMA_LLM_PROVIDER=smoke
export BIOPHARMA_LLM_MODEL=smoke-model
```

Run a local end-to-end workflow that archives raw text and writes structured results to JSONL:

```bash
PYTHONPATH=src python3 -m biopharma_agent.cli run-local \
  --file samples/news.txt \
  --source-name manual \
  --archive-dir data/raw \
  --output data/processed/insights.jsonl
```

Run deterministic local analysis and write feedback without an LLM:

```bash
echo "A biotech company raised financing, but clinical failure risk remains." \
  | PYTHONPATH=src python3 -m biopharma_agent.cli analyze-deterministic --stdin

PYTHONPATH=src python3 -m biopharma_agent.cli analyze-timeseries 1 2 3 100
PYTHONPATH=src python3 -m biopharma_agent.cli intelligence-brief --input data/processed/insights.jsonl
PYTHONPATH=src python3 -m biopharma_agent.cli intelligence-brief \
  --input data/processed/insights.jsonl \
  --output-md data/reports/latest_brief.md \
  --output-json data/reports/latest_brief.json

PYTHONPATH=src python3 -m biopharma_agent.cli feedback \
  --document-id doc-1 \
  --reviewer analyst \
  --decision accept

PYTHONPATH=src python3 -m biopharma_agent.cli seed-demo
```

List and fetch built-in RSS/Atom sources:

```bash
PYTHONPATH=src python3 -m biopharma_agent.cli list-sources
PYTHONPATH=src python3 -m biopharma_agent.cli list-sources --category industry_news
PYTHONPATH=src python3 -m biopharma_agent.cli list-source-profiles
PYTHONPATH=src python3 -m biopharma_agent.cli fetch-source fda_press_releases --limit 2

# After configuring LLM environment variables, fetch and analyze directly.
PYTHONPATH=src python3 -m biopharma_agent.cli fetch-sources \
  --profile core_intelligence \
  --limit 1 \
  --fetch-details \
  --clean-html-details \
  --incremental \
  --analyze
```

`fetch-sources` dispatches by source metadata to the correct collector: RSS/Atom, HTML listing, ASX announcements, or SEC submissions. ASX defaults to the `CSL/COH/RMD` watchlist. SEC defaults to Pfizer, Moderna, Amgen, Gilead, and Regeneron filings for `8-K/10-K/10-Q/S-1/424B*`. FDA press releases and MedWatch use official RSS feeds; `--fetch-details` deep-fetches detail pages and can clean main body text.

Source profiles provide reusable bundles for common workflows. Current profiles include `core_intelligence`, `global_safety_alerts`, `market_filings`, and `industry_news`. Use `--profile` with `fetch-sources` or `scheduled-fetch`; explicit `--sources` override the profile when both are provided.

Run the full daily intelligence cycle in one command:

```bash
PYTHONPATH=src python3 -m biopharma_agent.cli daily-cycle \
  --profile core_intelligence \
  --limit 1 \
  --incremental \
  --report-md data/reports/latest_brief.md \
  --report-json data/reports/latest_brief.json
```

The daily cycle fetches the selected profile, analyzes documents by default, updates source state, writes a cycle run log to `data/runs/daily_cycles.jsonl`, generates the intelligence brief, and saves Markdown/JSON report artifacts. Use `--no-analyze` for a collection-and-report smoke run that does not call an LLM.

Each collection command updates source state by default with the latest source status, selected document IDs, skipped duplicate count, consecutive failure count, failure diagnosis, and remediation hint. JSONL mode writes `data/runs/source_state.json`; PostgreSQL mode writes the same state to the `source_states` table. Use `--incremental` to skip documents whose IDs are already recorded for that source. Use `--state-path` for a different JSONL state file, `--no-update-state` for stateless test runs, and `source-state` to inspect health:

```bash
PYTHONPATH=src python3 -m biopharma_agent.cli source-state
PYTHONPATH=src python3 -m biopharma_agent.cli source-report
PYTHONPATH=src python3 -m biopharma_agent.cli fetch-source fda_press_releases \
  --limit 5 \
  --incremental
```

Fetch HTML listing sources:

```bash
PYTHONPATH=src python3 -m biopharma_agent.cli list-sources --kind industry_news_html
PYTHONPATH=src python3 -m biopharma_agent.cli list-sources --kind market_announcement_html
PYTHONPATH=src python3 -m biopharma_agent.cli fetch-html-source news_medical_life_sciences --limit 5
PYTHONPATH=src python3 -m biopharma_agent.cli fetch-html-source investegate_announcements \
  --limit 2 \
  --fetch-details \
  --clean-html-details
PYTHONPATH=src python3 -m biopharma_agent.cli fetch-html-sources --limit 3
```

HTML sources can be marked `enabled=false` in metadata. News-Medical is kept as a candidate because robots.txt currently blocks the listing page, while Investegate announcement listing collection has been verified. By default, HTML collection stores listing item titles and links. `--fetch-details` fetches each detail page, and `--clean-html-details` converts full-page HTML into main body text to reduce navigation and footer noise.

JSONL is the default output format. The local repository idempotently replaces results with the same `source + document_id + checksum + provider + model`. Use `--append-duplicates` on `run-local` or `run-url` when repeated analyses should be preserved.

Lightweight scheduling can run once for cron-style jobs or loop locally:

```bash
# Run once and write data/runs/fetch_runs.jsonl.
PYTHONPATH=src python3 -m biopharma_agent.cli scheduled-fetch \
  --profile global_safety_alerts \
  --limit 2 \
  --max-runs 1 \
  --fetch-details \
  --clean-html-details

# Run every hour until stopped.
PYTHONPATH=src python3 -m biopharma_agent.cli scheduled-fetch \
  --limit 2 \
  --interval-seconds 3600 \
  --max-runs 0
```

PostgreSQL storage is optional. When enabled, the document inbox uses SQL-level filtering, counts, pagination, and facets. Human review records are stored in the `feedback` table:

```bash
python3 -m pip install "psycopg[binary]>=3"
docker compose up -d postgres
export BIOPHARMA_STORAGE_BACKEND=postgres
export BIOPHARMA_POSTGRES_DSN="postgresql://biopharma:biopharma@127.0.0.1:55432/biopharma_agent"
PYTHONPATH=src python3 -m biopharma_agent.cli migrate-postgres
scripts/run_postgres_integration.sh
```

`migrate-postgres` idempotently applies `infra/postgres/schema.sql`, then applies incremental SQL files in `infra/postgres/migrations`, and writes checksums to `schema_migrations`. If Docker Compose is not used, manually create a database and run the same migration command.

MinIO/S3 raw-document archiving is optional:

```bash
python3 -m pip install "boto3>=1.34"
docker compose up -d minio minio-init
export BIOPHARMA_RAW_ARCHIVE_BACKEND=minio
export BIOPHARMA_RAW_ARCHIVE_S3_BUCKET=biopharma-raw
export BIOPHARMA_RAW_ARCHIVE_S3_ENDPOINT_URL=http://127.0.0.1:9000
export BIOPHARMA_RAW_ARCHIVE_S3_ACCESS_KEY_ID=minioadmin
export BIOPHARMA_RAW_ARCHIVE_S3_SECRET_ACCESS_KEY=minioadmin
scripts/run_minio_smoke.sh
```

Knowledge graph writes default to local JSONL under `data/graph`. To write directly to Neo4j, install the driver and set the graph backend:

```bash
python3 -m pip install "neo4j>=5"
export BIOPHARMA_GRAPH_BACKEND=neo4j
export BIOPHARMA_NEO4J_URI=bolt://127.0.0.1:7687
export BIOPHARMA_NEO4J_USER=neo4j
export BIOPHARMA_NEO4J_PASSWORD=...
```

PostgreSQL + MinIO + real collection full-stack smoke:

```bash
python3 -m pip install "psycopg[binary]>=3" "boto3>=1.34"
scripts/run_storage_smoke.sh
scripts/run_full_stack_smoke.sh
```

`run_storage_smoke.sh` starts or reuses PostgreSQL and MinIO, applies migrations, checks SQL storage, and verifies a MinIO object without touching external news sources. CI runs this script on push and pull request.

`run_full_stack_smoke.sh` starts or reuses PostgreSQL and MinIO, applies the PostgreSQL migration, verifies SQL storage and S3-compatible raw archiving, fetches one real FDA press-release item, runs deterministic smoke-provider analysis, asserts a PostgreSQL insight row exists, and verifies the MinIO raw object with `head_object`. Set `PYTHON=/path/to/python` to choose the runtime; otherwise the script prefers the active virtualenv, then `.venv/bin/python`, then `python3`.

Airflow DAG smoke uses the Docker Compose profile to start the official Airflow image and run the `biopharma_fetch_sources` DAG:

```bash
scripts/run_airflow_smoke.sh
```

The Airflow smoke validates DAG import, executes `biopharma_fetch_sources` once, checks that the latest run log entry succeeded, and asserts at least one document was selected.

Start the local web workbench:

```bash
PYTHONPATH=src python3 -m biopharma_agent.cli serve --host 127.0.0.1 --port 8765
```

Then visit `http://127.0.0.1:8765`. The workbench includes document analysis, document inbox, market intelligence briefs, run monitoring, manual fetch triggers, one-click daily intelligence cycles, LLM extraction, task routing, human feedback, feedback browsing, time-series analysis, model settings, and runtime diagnostics. The inbox supports filtering by source, event type, risk, and keyword, plus pagination and sorting. The market panel can summarize stored analysis results into a Markdown intelligence brief. The run monitor can trigger selected sources, run the daily cycle, enable incremental collection, show source health, failure diagnosis, prioritized source alerts, and generate a Markdown source health report from the source state and run log. It uses the configured LLM for real analysis by default. If the API key is missing, the job fails and writes a run log for troubleshooting. Runtime diagnostics check LLM, storage, raw archive, sources, Docker, and GitHub sync state. The diagnostics API reports whether credentials are present but never returns secret values.

## Architecture Entry Points

- LLM types: [src/biopharma_agent/llm/types.py](src/biopharma_agent/llm/types.py)
- Provider factory: [src/biopharma_agent/llm/factory.py](src/biopharma_agent/llm/factory.py)
- Analysis pipeline: [src/biopharma_agent/analysis/pipeline.py](src/biopharma_agent/analysis/pipeline.py)
- Module contracts: [src/biopharma_agent/contracts.py](src/biopharma_agent/contracts.py)
- Local workflow: [src/biopharma_agent/orchestration/workflow.py](src/biopharma_agent/orchestration/workflow.py)
- Storage repository interface: [src/biopharma_agent/storage/repository.py](src/biopharma_agent/storage/repository.py)
- Feedback repository interface: [src/biopharma_agent/ops/feedback.py](src/biopharma_agent/ops/feedback.py)
- PostgreSQL schema: [infra/postgres/schema.sql](infra/postgres/schema.sql)
- PostgreSQL local environment: [compose.yaml](compose.yaml)
- MinIO raw archive: [infra/minio/README.md](infra/minio/README.md)
- Airflow orchestration wrapper: [infra/airflow/README.md](infra/airflow/README.md)
- Web workbench: [src/biopharma_agent/web/server.py](src/biopharma_agent/web/server.py)
- Execution plan: [docs/execution_plan.md](docs/execution_plan.md)

## Verification Snapshot

Latest local verification on May 1, 2026:

- Unit tests: `PYTHONPATH=src python -m unittest discover -s tests` -> 115 passed, 1 skipped
- Storage smoke: `scripts/run_storage_smoke.sh` -> PostgreSQL and MinIO checks passed without external news-source dependency
- Full-stack smoke: `scripts/run_full_stack_smoke.sh` -> PostgreSQL migration checked, MinIO raw object verified, FDA real collection selected 1 document and analyzed 1 document
- Airflow smoke: `scripts/run_airflow_smoke.sh` -> DAG loaded, latest run log entry succeeded with 1 selected document, and source state was written
- Content hygiene: tracked files contain no Chinese text, real host name, real local user name, or committed API key
