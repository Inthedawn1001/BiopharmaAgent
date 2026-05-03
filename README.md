# Biopharma Agent

Biopharma Agent is a local-first intelligence workbench for tracking biopharma
industry news, regulatory updates, safety alerts, and capital-market filings.
It can collect public source material, run LLM-assisted extraction, generate
daily intelligence briefs, track source health, and give analysts a browser
interface for review.

The project is designed for analysts, operators, and builders who want a
practical pipeline they can run locally first, then connect to production
storage, schedulers, and model providers when ready.

> This tool is for research and workflow automation. It is not medical,
> investment, or legal advice.

## What You Can Do

- Analyze pasted text, local files, or URLs with a configured LLM.
- Fetch built-in biopharma and market sources such as FDA feeds, EMA news, SEC
  EDGAR submissions, ASX announcements, and selected industry news feeds.
- Run a daily intelligence cycle that collects, analyzes, updates source health,
  writes a run log, and creates a Markdown/JSON brief.
- Review documents, risks, events, source health, run history, and feedback in
  the local Web Workbench.
- Use JSONL by default, or switch to PostgreSQL, MinIO/S3 archiving, and
  optional graph outputs.
- Deploy the static Workbench shell to Netlify and proxy API calls to a running
  Python backend.

## Live Static Workbench

A static Netlify deployment is available here:

[https://biopharma-agent-workbench-20260503185717-376.netlify.app](https://biopharma-agent-workbench-20260503185717-376.netlify.app)

The Netlify site serves the Workbench frontend and a lightweight API proxy. To
use real collection and LLM actions from Netlify, deploy the Python API service
elsewhere and set `BIOPHARMA_API_ORIGIN` in Netlify environment variables.

## Requirements

- Python 3.10+
- Git
- Optional: Docker Desktop for PostgreSQL, MinIO, and Airflow smoke tests
- Optional: Node/npm for Netlify deployments

The default local JSONL mode has no required third-party Python dependencies.
Install optional extras only when you need production-shaped storage or object
archiving.

## Install

```bash
git clone https://github.com/Inthedawn1001/BiopharmaAgent.git
cd BiopharmaAgent

python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

If you prefer not to install the package, prefix commands with `PYTHONPATH=src`
and run `python3 -m biopharma_agent.cli ...`.

Check that the runtime is healthy:

```bash
biopharma-agent diagnose
biopharma-agent list-sources
biopharma-agent list-source-profiles
```

## Configure An LLM

Biopharma Agent supports OpenAI-compatible APIs, Anthropic, Gemini, Ollama,
custom HTTP endpoints, and a deterministic `smoke` provider for keyless tests.

DeepSeek example:

```bash
export BIOPHARMA_LLM_PROVIDER=custom
export BIOPHARMA_LLM_BASE_URL=https://api.deepseek.com
export BIOPHARMA_LLM_MODEL=deepseek-chat
export BIOPHARMA_LLM_API_KEY=...

biopharma-agent llm-check
```

OpenAI example:

```bash
export BIOPHARMA_LLM_PROVIDER=openai
export BIOPHARMA_LLM_BASE_URL=https://api.openai.com/v1
export BIOPHARMA_LLM_MODEL=gpt-4.1-mini
export BIOPHARMA_LLM_API_KEY=...

biopharma-agent llm-check
```

Local smoke-provider example:

```bash
export BIOPHARMA_LLM_PROVIDER=smoke
export BIOPHARMA_LLM_MODEL=smoke-model

biopharma-agent llm-check
```

Secrets should stay in your shell, local secret manager, deployment environment,
or the Workbench runtime form. Do not commit API keys.

## Start The Web Workbench

```bash
biopharma-agent serve --host 127.0.0.1 --port 8765
```

Open:

[http://127.0.0.1:8765](http://127.0.0.1:8765)

The Workbench includes:

- Document Analysis: local analysis, LLM extraction, and task routing
- Document Inbox: search, filters, sorting, pagination, and document details
- Run Monitor: manual fetches, daily cycles, retries, and source health
- Market Intelligence: Markdown/JSON briefs and simple time-series analysis
- Human Review: analyst feedback capture
- Model Settings: provider/model/base URL/API key input and live LLM check
- Runtime Diagnostics: secret-safe environment, storage, Docker, and Git status

The sidebar supports English and Chinese UI switching.

## Run A Daily Intelligence Cycle

The daily cycle is the main operating command. It fetches a source profile,
analyzes selected documents, updates source state, writes a run log, and creates
brief artifacts.

```bash
biopharma-agent daily-cycle \
  --profile core_intelligence \
  --limit 1 \
  --incremental \
  --fetch-details \
  --clean-html-details \
  --report-md data/reports/latest_brief.md \
  --report-json data/reports/latest_brief.json
```

Use `--no-analyze` for a collection-only smoke run that does not call an LLM:

```bash
biopharma-agent daily-cycle \
  --profile core_intelligence \
  --limit 1 \
  --no-analyze
```

Validate the output before handing it to an analyst:

```bash
biopharma-agent quality-gate \
  --analysis-path data/processed/insights.jsonl \
  --brief-md data/reports/latest_brief.md \
  --source-state data/runs/source_state.json \
  --require-brief \
  --require-source-state
```

## Fetch Sources Manually

List available sources and profiles:

```bash
biopharma-agent list-sources
biopharma-agent list-source-profiles
```

Fetch and analyze one item per core source:

```bash
biopharma-agent fetch-sources \
  --profile core_intelligence \
  --limit 1 \
  --fetch-details \
  --clean-html-details \
  --incremental \
  --analyze
```

Fetch a single source without LLM analysis:

```bash
biopharma-agent fetch-source fda_press_releases --limit 2
```

Current source profiles include:

- `core_intelligence`
- `global_safety_alerts`
- `market_filings`
- `industry_news`

Collection dispatch is source-aware. RSS/Atom feeds, HTML listings, ASX
announcements, and SEC submissions use different collectors behind the same
CLI and Workbench controls.

## Analyze Your Own Material

Analyze pasted text with the configured LLM:

```bash
echo "A biotech company completed Series B financing and advanced a PD-1 phase 2 program." \
  | biopharma-agent analyze-text --stdin
```

Run deterministic local analysis without an LLM:

```bash
echo "A biotech company raised financing, but clinical failure risk remains." \
  | biopharma-agent analyze-deterministic --stdin
```

Archive and analyze a local document:

```bash
cat report.txt | biopharma-agent run-local \
  --stdin \
  --source-name manual \
  --title "Analyst note" \
  --archive-dir data/raw \
  --output data/processed/insights.jsonl
```

Fetch and analyze a URL:

```bash
biopharma-agent run-url https://example.com/news-item --source-name example
```

## Generate Briefs And Reports

Create a Markdown and JSON intelligence brief from stored analysis records:

```bash
biopharma-agent intelligence-brief \
  --input data/processed/insights.jsonl \
  --output-md data/reports/latest_brief.md \
  --output-json data/reports/latest_brief.json
```

Inspect source health:

```bash
biopharma-agent source-state
biopharma-agent source-report
```

Record analyst feedback:

```bash
biopharma-agent feedback \
  --document-id doc-1 \
  --reviewer analyst \
  --decision accept
```

## Storage Options

### Local JSONL

JSONL is the default and is the easiest mode for local use. Analysis records,
feedback, source state, run logs, raw documents, and graph exports are written
under `data/`.

### PostgreSQL

Use PostgreSQL when you want SQL-level document filtering, pagination, facets,
and feedback storage.

```bash
python -m pip install -e ".[postgres]"
docker compose up -d postgres

export BIOPHARMA_STORAGE_BACKEND=postgres
export BIOPHARMA_POSTGRES_DSN="postgresql://biopharma:biopharma@127.0.0.1:55432/biopharma_agent"

biopharma-agent migrate-postgres
```

### MinIO Or S3-Compatible Raw Archive

```bash
python -m pip install -e ".[s3]"
docker compose up -d minio minio-init

export BIOPHARMA_RAW_ARCHIVE_BACKEND=minio
export BIOPHARMA_RAW_ARCHIVE_S3_BUCKET=biopharma-raw
export BIOPHARMA_RAW_ARCHIVE_S3_ENDPOINT_URL=http://127.0.0.1:9000
export BIOPHARMA_RAW_ARCHIVE_S3_ACCESS_KEY_ID=minioadmin
export BIOPHARMA_RAW_ARCHIVE_S3_SECRET_ACCESS_KEY=minioadmin
```

### Graph Output

Local graph-shaped JSONL exports are written under `data/graph` by default.
Neo4j can be enabled with the optional driver and `BIOPHARMA_GRAPH_*`
environment variables.

## Scheduling And Production-Shaped Runs

Run one scheduled fetch for cron-like jobs:

```bash
biopharma-agent scheduled-fetch \
  --profile global_safety_alerts \
  --limit 2 \
  --max-runs 1 \
  --fetch-details \
  --clean-html-details
```

Run the Docker-backed smoke checks:

```bash
scripts/run_storage_smoke.sh
scripts/run_full_stack_smoke.sh
scripts/run_airflow_smoke.sh
```

The Airflow wrapper delegates to the same CLI daily-cycle flow. See
[infra/airflow/README.md](infra/airflow/README.md) for scheduler settings.

## Netlify Deployment

This repository includes a Netlify configuration for the static Workbench:

- `netlify.toml` publishes `src/biopharma_agent/web/static`
- `netlify/functions/api-proxy.js` proxies `/api/*` to `BIOPHARMA_API_ORIGIN`

Deploy:

```bash
npx netlify status
npx netlify deploy --prod
```

If `BIOPHARMA_API_ORIGIN` is not configured on Netlify, the static Workbench
still loads, but API actions return a clear backend-not-configured message.

## Data, Security, And Compliance

- Respect source terms, rate limits, and robots.txt.
- Keep API keys and credentials out of Git.
- Treat generated intelligence as analyst-supporting material, not final advice.
- Review high-impact medical, regulatory, legal, or investment conclusions
  before use.
- Use source health and the quality gate to catch stale sources, blocked pages,
  weak body extraction, and missing risk/event coverage.

## Useful Project Links

- Production runbook: [docs/production_runbook.md](docs/production_runbook.md)
- Architecture notes: [docs/architecture.md](docs/architecture.md)
- Execution plan: [docs/execution_plan.md](docs/execution_plan.md)
- PostgreSQL schema: [infra/postgres/schema.sql](infra/postgres/schema.sql)
- Docker Compose services: [compose.yaml](compose.yaml)
- Web Workbench server: [src/biopharma_agent/web/server.py](src/biopharma_agent/web/server.py)
- LLM providers: [src/biopharma_agent/llm/providers](src/biopharma_agent/llm/providers)

## 中文快速说明

Biopharma Agent 是一个面向生物医药产业与资本市场情报的本地优先工作台。
你可以用它抓取 FDA、EMA、SEC、ASX 和行业新闻等公开信息，调用 DeepSeek、
OpenAI 或其他兼容模型做结构化抽取，并生成每日情报简报。

最常用的启动方式：

```bash
biopharma-agent serve --host 127.0.0.1 --port 8765
```

打开 `http://127.0.0.1:8765` 后，可以在侧边栏切换 `EN / 中文`。在“模型设置”
中可以选择 DeepSeek/OpenAI/OpenAI-compatible，填写模型、Base URL 和 API Key，
再运行连接检查。前端输入的 Key 只保存在当前服务进程中，不会写入仓库文件。

运行每日情报循环：

```bash
biopharma-agent daily-cycle \
  --profile core_intelligence \
  --limit 1 \
  --incremental \
  --fetch-details \
  --clean-html-details \
  --report-md data/reports/latest_brief.md \
  --report-json data/reports/latest_brief.json
```
