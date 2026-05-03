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
- Daily intelligence cycle command and Airflow wrapper for fetch, analysis, source-state, and brief generation
- Production quality gate for analysis, brief, and source-health artifacts
- CLI commands for model checks, analysis, execution plans, migrations, and diagnostics
- Dependency-light unit tests
- GitHub Actions CI for hygiene, unit-test, storage-smoke, and fixture quality-gate checks

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

Validate generated artifacts before operator use:

```bash
PYTHONPATH=src python3 -m biopharma_agent.cli quality-gate \
  --analysis-path data/processed/insights.jsonl \
  --brief-md data/reports/latest_brief.md \
  --source-state data/runs/source_state.json \
  --require-brief \
  --require-source-state
```

The quality gate exits `0` only when the analysis repository has enough records, structured summaries/events/risks are populated, body text is usable, the Markdown brief contains the expected sections, and source-state failures are within threshold. Use `--json` for automation output.

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

The Airflow smoke runs the DAG in `daily-cycle` mode by default. It validates DAG import, executes `biopharma_fetch_sources` once, checks that the latest daily-cycle run log entry succeeded, asserts at least one document was selected, and verifies Markdown/JSON brief artifacts. Set `BIOPHARMA_AIRFLOW_MODE=scheduled-fetch` to exercise the legacy collection-only wrapper. See [infra/airflow/README.md](infra/airflow/README.md) for production scheduler environment variables.

Start the local web workbench:

```bash
PYTHONPATH=src python3 -m biopharma_agent.cli serve --host 127.0.0.1 --port 8765
```

Then visit `http://127.0.0.1:8765`. The workbench includes document analysis, document inbox, market intelligence briefs, run monitoring, manual fetch triggers, one-click daily intelligence cycles, LLM extraction, task routing, human feedback, feedback browsing, time-series analysis, model settings, and runtime diagnostics. The inbox supports filtering by source, event type, risk, and keyword, plus pagination and sorting. The market panel can summarize stored analysis results into a Markdown intelligence brief. The run monitor can trigger selected sources, run the daily cycle, enable incremental collection, show source health, failure diagnosis, prioritized source alerts, and generate a Markdown source health report from the source state and run log. It uses the configured LLM for real analysis by default. If the API key is missing, the job fails and writes a run log for troubleshooting. The Model Settings page can switch providers, edit the OpenAI-compatible base URL/model, enter an API key, and run a live connection check. UI-entered keys are applied only to the current workbench process and are never returned by the API or written to repository files. Runtime diagnostics check LLM, storage, raw archive, sources, Docker, and GitHub sync state. The diagnostics API reports whether credentials are present but never returns secret values. The sidebar language switcher can toggle the workbench between English and Chinese; the preference is saved in the browser.

See [docs/production_runbook.md](docs/production_runbook.md) for the recommended daily operating loop, storage profiles, Airflow settings, readiness gate, and failure handling.

## 中文说明

Biopharma Agent 是一个面向生物医药产业与资本市场情报的本地 Agent 工具。当前主线已经形成完整闭环：抓取权威数据源、调用配置好的大语言模型进行结构化分析、维护来源健康状态、生成每日情报简报，并通过质量闸门检查输出是否足够可靠。

快速启动本地工作台：

```bash
PYTHONPATH=src python3 -m biopharma_agent.cli serve --host 127.0.0.1 --port 8765
```

打开 `http://127.0.0.1:8765` 后，可以在左侧边栏使用 `EN / 中文` 切换界面语言。中文界面覆盖文档分析、文档收件箱、运行监控、人工复核、时间序列、模型设置和运行诊断等主要操作区。

运行每日情报循环：

```bash
PYTHONPATH=src python3 -m biopharma_agent.cli daily-cycle \
  --profile core_intelligence \
  --limit 1 \
  --incremental \
  --report-md data/reports/latest_brief.md \
  --report-json data/reports/latest_brief.json
```

运行质量闸门：

```bash
PYTHONPATH=src python3 -m biopharma_agent.cli quality-gate \
  --analysis-path data/processed/insights.jsonl \
  --brief-md data/reports/latest_brief.md \
  --source-state data/runs/source_state.json \
  --require-brief \
  --require-source-state
```

实际调用模型前，可以通过环境变量配置 `BIOPHARMA_LLM_PROVIDER`、`BIOPHARMA_LLM_BASE_URL`、`BIOPHARMA_LLM_MODEL` 和 `BIOPHARMA_LLM_API_KEY`，也可以在工作台的“模型设置”页面选择 DeepSeek/OpenAI/OpenAI-compatible 等供应商并输入 API Key。前端输入的密钥只会写入当前服务进程的运行期环境，不会回传到 API 响应，也不会保存到仓库文件。密钥仍应只保存在本地环境、运行期表单或密钥管理系统中，不要提交到仓库。

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

Latest local verification on May 2, 2026:

- Unit tests: `PYTHONPATH=src python -m unittest discover -s tests` -> 144 passed, 1 skipped
- Storage smoke: `scripts/run_storage_smoke.sh` -> PostgreSQL and MinIO checks passed without external news-source dependency
- Full-stack smoke: `scripts/run_full_stack_smoke.sh` -> PostgreSQL migration checked, MinIO raw object verified, FDA real collection selected 1 document and analyzed 1 document
- Airflow smoke: `scripts/run_airflow_smoke.sh` -> DAG loaded, daily cycle succeeded with 1 selected document, source state was written, and brief artifacts were generated
- Content hygiene: tracked files contain no real host name, real local user name, or committed API key. Chinese text is intentionally present in the bilingual UI and README.
