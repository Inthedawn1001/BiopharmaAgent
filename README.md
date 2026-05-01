# Biopharma Agent

面向生物医药产业与资本市场信息的 agent 工具骨架。

当前版本已经落地 LLM 能力层、RSS 数据源采集、本地端到端分析流程、JSONL/可选 PostgreSQL 存储接口、本地/S3 兼容原始文档归档、图谱导出和本地 Web 工作台。调度、Neo4j 在线写入和更深入的 NLP/时序建模仍按模块预留扩展点，后续可以继续接入 Scrapy、Airflow、PostgreSQL、Neo4j、spaCy、LDA、ARIMA 等组件。

## 已实现

- 统一 LLM 请求/响应类型
- OpenAI-compatible、Anthropic、Gemini、Ollama、自定义 HTTP 适配器
- Chat、embedding、JSON schema 结构化输出能力抽象
- 生物医药与资本市场文档分析管线
- RSS/Atom、HTML listing、ASX 公告、SEC EDGAR submissions 数据源抓取和端到端入库流程
- 内置数据源目录包含监管、行业新闻和市场新闻源，并带 category/priority/rate-limit 元数据
- HTML listing adapter 支持没有稳定 RSS 的页面型来源，先抽取列表链接进入管线
- JSONL 本地仓储、幂等写入、PostgreSQL schema/adapter 和 SQL 级分页查询
- 人工反馈仓储支持 JSONL 与 PostgreSQL 两种后端
- 原始文档归档支持本地文件系统与 S3/MinIO 兼容对象存储
- 轻量调度命令支持一次性/循环抓取，并记录 JSONL run log
- 图谱节点/边 JSONL 导出，便于后续导入 Neo4j
- 本地 Web 工作台：文档分析、文档收件箱、运行监控、手动触发抓取、人工复核、时序分析、模型配置查看、运行诊断
- CLI：检查模型、分析文本、打印执行计划、输出运行诊断
- 无第三方依赖的单元测试

## 快速开始

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
PYTHONPATH=src python3 -m biopharma_agent.cli plan
PYTHONPATH=src python3 -m biopharma_agent.cli diagnose
```

配置环境变量后可以调用真实模型：

```bash
export BIOPHARMA_LLM_PROVIDER=openai
export BIOPHARMA_LLM_BASE_URL=https://api.openai.com/v1
export BIOPHARMA_LLM_API_KEY=...
export BIOPHARMA_LLM_MODEL=gpt-4.1-mini

echo "某生物技术公司宣布完成B轮融资并推进PD-1项目临床II期。" \
  | PYTHONPATH=src python3 -m biopharma_agent.cli analyze-text --stdin
```

本地 Ollama 示例：

```bash
export BIOPHARMA_LLM_PROVIDER=ollama
export BIOPHARMA_LLM_BASE_URL=http://localhost:11434
export BIOPHARMA_LLM_MODEL=qwen2.5:7b

PYTHONPATH=src python3 -m biopharma_agent.cli llm-check
```

DeepSeek 示例：

```bash
export BIOPHARMA_LLM_PROVIDER=custom
export BIOPHARMA_LLM_BASE_URL=https://api.deepseek.com
export BIOPHARMA_LLM_MODEL=deepseek-chat
export BIOPHARMA_LLM_API_KEY=...

PYTHONPATH=src python3 -m biopharma_agent.cli llm-check
```

运行本地端到端流程，将原始文本归档并把结构化结果写入 JSONL：

```bash
PYTHONPATH=src python3 -m biopharma_agent.cli run-local \
  --file samples/news.txt \
  --source-name manual \
  --archive-dir data/raw \
  --output data/processed/insights.jsonl
```

无需 LLM 的本地分析与反馈记录：

```bash
echo "测试生物融资增长，但存在临床失败风险" \
  | PYTHONPATH=src python3 -m biopharma_agent.cli analyze-deterministic --stdin

PYTHONPATH=src python3 -m biopharma_agent.cli analyze-timeseries 1 2 3 100

PYTHONPATH=src python3 -m biopharma_agent.cli feedback \
  --document-id doc-1 \
  --reviewer analyst \
  --decision accept

PYTHONPATH=src python3 -m biopharma_agent.cli seed-demo
```

查看和抓取内置 RSS/Atom 数据源：

```bash
PYTHONPATH=src python3 -m biopharma_agent.cli list-sources
PYTHONPATH=src python3 -m biopharma_agent.cli list-sources --category industry_news
PYTHONPATH=src python3 -m biopharma_agent.cli fetch-source fda_press_releases --limit 2

# 配置 LLM 环境变量后，可直接抓取并分析入库
PYTHONPATH=src python3 -m biopharma_agent.cli fetch-sources \
  --sources fda_press_releases biopharma_dive_news sec_biopharma_filings asx_biopharma_announcements \
  --limit 1 \
  --fetch-details \
  --clean-html-details \
  --analyze
```

`fetch-sources` 会按 source metadata 自动选择采集器：普通 RSS/Atom、HTML listing、
ASX announcements 或 SEC submissions。ASX 默认 watchlist 为 `CSL/COH/RMD`；
SEC 默认覆盖 Pfizer、Moderna、Amgen、Gilead、Regeneron 的 `8-K/10-K/10-Q/S-1/424B*`
类 filings。FDA press releases 和 MedWatch 仍使用官方 RSS，加 `--fetch-details`
可继续抓详情页并清洗正文。

抓取 HTML 列表页来源：

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

HTML 源可以在 metadata 中标记 `enabled=false`。例如 News-Medical 当前因
robots.txt 限制保留为候选源，不会被默认批量抓取；Investegate 公告列表已验证可抓取。
默认 HTML 抓取只保存列表项标题和链接；加 `--fetch-details` 会继续抓取详情页。再加
`--clean-html-details` 会将详情页从全页 HTML 清洗成主正文文本，减少导航、页脚等噪声。

默认写入 JSONL，并会对同一 `source + document_id + checksum + provider + model` 做幂等替换。若需要保留重复分析记录，可在 `run-local` 或 `run-url` 中使用 `--append-duplicates`。

轻量调度入口，可作为 cron 的单次任务，也可以本地循环运行：

```bash
# 单次执行并记录 data/runs/fetch_runs.jsonl
PYTHONPATH=src python3 -m biopharma_agent.cli scheduled-fetch \
  --sources fda_press_releases biopharma_dive_news \
  --limit 2 \
  --max-runs 1 \
  --fetch-details \
  --clean-html-details

# 每小时持续执行，直到手动停止
PYTHONPATH=src python3 -m biopharma_agent.cli scheduled-fetch \
  --limit 2 \
  --interval-seconds 3600 \
  --max-runs 0
```

PostgreSQL 存储可选启用，文档收件箱会使用 SQL 级过滤、计数、分页和 facets；人工复核记录也会写入 `feedback` 表：

```bash
python3 -m pip install "psycopg[binary]>=3"
docker compose up -d postgres
export BIOPHARMA_STORAGE_BACKEND=postgres
export BIOPHARMA_POSTGRES_DSN="postgresql://biopharma:biopharma@127.0.0.1:55432/biopharma_agent"
scripts/run_postgres_integration.sh
```

如果不用 Docker Compose，也可以手动创建数据库并执行 `infra/postgres/schema.sql`。

MinIO/S3 原始文档归档可选启用：

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

PostgreSQL + MinIO + 真实采集的全链路 smoke：

```bash
python3 -m pip install "psycopg[binary]>=3" "boto3>=1.34"
scripts/run_full_stack_smoke.sh
```

Airflow DAG smoke 会通过 Docker Compose profile 启动官方 Airflow 镜像并执行
`biopharma_fetch_sources` DAG：

```bash
scripts/run_airflow_smoke.sh
```

启动本地 Web 工作台：

```bash
PYTHONPATH=src python3 -m biopharma_agent.cli serve --host 127.0.0.1 --port 8765
```

然后访问 `http://127.0.0.1:8765`。工作台包含文档分析、历史文档收件箱、运行监控、手动触发抓取、LLM 抽取、任务路由、人工反馈、反馈记录浏览、时序分析、模型配置查看和运行诊断。收件箱支持按来源、事件类型、风险等级和关键词筛选，并支持分页与排序。“运行监控”页可以选择数据源并触发抓取，默认会调用已配置的 LLM 做真实分析；未配置 API key 时，该任务会失败并写入 run log，方便排障。“运行诊断”页会检查 LLM、存储、原始归档、数据源、Docker 和 GitHub 同步状态；该接口只返回密钥是否存在，不会返回密钥值。

## 架构入口

- LLM 类型定义：[src/biopharma_agent/llm/types.py](src/biopharma_agent/llm/types.py)
- Provider 工厂：[src/biopharma_agent/llm/factory.py](src/biopharma_agent/llm/factory.py)
- 分析管线：[src/biopharma_agent/analysis/pipeline.py](src/biopharma_agent/analysis/pipeline.py)
- 模块契约：[src/biopharma_agent/contracts.py](src/biopharma_agent/contracts.py)
- 本地工作流：[src/biopharma_agent/orchestration/workflow.py](src/biopharma_agent/orchestration/workflow.py)
- 存储仓储接口：[src/biopharma_agent/storage/repository.py](src/biopharma_agent/storage/repository.py)
- 反馈仓储接口：[src/biopharma_agent/ops/feedback.py](src/biopharma_agent/ops/feedback.py)
- PostgreSQL schema：[infra/postgres/schema.sql](infra/postgres/schema.sql)
- PostgreSQL 本地环境：[compose.yaml](compose.yaml)
- MinIO 原始归档：[infra/minio/README.md](infra/minio/README.md)
- Airflow 调度包装：[infra/airflow/README.md](infra/airflow/README.md)
- Web 工作台：[src/biopharma_agent/web/server.py](src/biopharma_agent/web/server.py)
- 执行计划：[docs/execution_plan.md](docs/execution_plan.md)
