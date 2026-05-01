# Architecture

## Layered Design

The system is split into five replaceable modules:

1. Collection: crawlers, source adapters, document fetchers.
2. Parsing: HTML/PDF normalization, language detection, metadata extraction.
3. Storage: raw archive, relational metadata, graph relations.
4. Analysis: NLP, time series, topic models, LLM-assisted extraction.
5. Presentation: APIs, dashboards, human review queues.

The LLM layer is intentionally separate. It can be used by parsing, analysis,
agent planning, QA, and human-review workflows without tying the rest of the
system to one model vendor.

## Source Catalog

Feed sources are stored as `SourceRef` entries with operational metadata:
category, priority, polling interval, per-source request delay, and robots
preferences. `list-sources` exposes the catalog and can filter by kind or
category. Batch collection uses priority ordering by default, which gives
regulatory and safety sources precedence over lower urgency industry feeds.

Sources can declare a collector type. RSS/Atom sources use the feed collector;
HTML listing sources declare `collector=html_listing` and provide link
extraction rules such as URL include/exclude patterns, title keywords, and
maximum link count. This keeps page-list extraction configurable while leaving
room for later dedicated adapters for JavaScript-heavy sites.

HTML listing sources can be disabled with a reason when robots.txt, client-side
rendering, or site-specific access rules make automated collection unsuitable.
Disabled sources remain visible in the catalog but are skipped by default batch
HTML collection.

HTML listing results can be converted into lightweight RawDocuments containing
only title and URL, or deep-fetched with `--fetch-details` so each discovered URL
is retrieved as a full raw HTML document while preserving listing metadata.
When `--clean-html-details` is set, detail pages are converted to main-content
text using semantic containers such as `<article>` and `<main>`, with a text
density fallback for simpler pages.

## LLM Layer

The LLM layer provides:

- A provider-neutral request model.
- Provider adapters for common API shapes.
- Structured output with JSON schema hints.
- Embeddings for future retrieval-augmented generation.
- Transport injection for tests, retries, and observability.

Supported provider families in this MVP:

- `openai`: OpenAI-compatible `/chat/completions` and `/embeddings`.
- `anthropic`: Claude Messages API.
- `gemini`: Gemini `generateContent` and embedding endpoints.
- `ollama`: Local Ollama chat and embedding APIs.
- `custom`: OpenAI-compatible defaults with configurable paths.
- `smoke`: deterministic local provider for infrastructure validation without external API keys.

## Data Contract

Documents move through a stable internal contract:

- `RawDocument`: source URL, raw text or bytes pointer, collected time.
- `ParsedDocument`: normalized text, metadata, language, checksum.
- `DocumentInsight`: summary, entities, events, relations, risk signals.
- `PipelineResult`: input document plus structured analysis output.

This lets crawlers, parsers, storage backends, and model providers evolve
independently.

## Storage Boundary

Analysis results are now written through an `AnalysisRepository` protocol.
The default implementation is JSONL for local development, with an idempotent
variant used by recurring collection commands. PostgreSQL can be enabled with
`BIOPHARMA_STORAGE_BACKEND=postgres` and `BIOPHARMA_POSTGRES_DSN`.

PostgreSQL tables separate source metadata, normalized documents, insight
payloads, entities, events, relations, risk signals, and feedback. The full
schema lives in `infra/postgres/schema.sql`. The `migrate-postgres` CLI command
applies that schema idempotently and records its checksum in `schema_migrations`,
so local Docker, smoke tests, Airflow wrappers, and later CI jobs can prepare
the database through the same entry point.

Document listing uses a shared filter contract. JSONL evaluates that contract
in process; PostgreSQL pushes source, event type, risk, keyword search, sorting,
pagination, counts, and facets into SQL. Human review records use the same
backend selection through a `FeedbackRepository` protocol.

Local PostgreSQL development is defined in `compose.yaml`. Optional integration
checks are skipped by default and enabled with `BIOPHARMA_RUN_POSTGRES_TESTS=1`
plus `BIOPHARMA_POSTGRES_DSN`.

## Raw Archive Boundary

Raw collected documents are written through a `RawArchive` protocol. The local
implementation stores `raw.txt` and `metadata.json` under `data/raw`; the
S3-compatible implementation writes the same pair of objects to AWS S3, MinIO,
or compatible object stores. CLI workflows use the raw archive factory, so
archival can move from local files to object storage without changing collection
or analysis code.

## Scheduling Boundary

Recurring collection is built around the `scheduled-fetch` CLI command and a
small `RecurringRunner`. The runner records every attempt to a JSONL run log
with status, timing, result, error, and metadata. This gives cron, local
development, and Airflow the same execution path: run the CLI once, or loop it
with an interval.

The Airflow DAG in `infra/airflow/dags` intentionally shells out to
`scheduled-fetch --max-runs 1`. Airflow handles external orchestration while the
agent keeps ownership of source selection, LLM configuration, storage, raw
archive, and graph settings.
