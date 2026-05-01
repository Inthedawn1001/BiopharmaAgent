# Execution Plan

## Phase 1: LLM MVP

- Build provider-neutral LLM types and interfaces.
- Implement OpenAI-compatible, Anthropic, Gemini, Ollama, and custom HTTP adapters.
- Build a structured extraction pipeline for biopharma and capital-market text.
- Add CLI commands for smoke testing and local development.
- Add unit tests with fake transports and fake providers.

## Phase 2: Data Contracts and Local Pipeline

- Finalize source, raw document, parsed document, and analysis result contracts.
- Implement local filesystem raw archive.
- Add deterministic parsers for plain text and HTML.
- Add idempotent checksum-based deduplication.

## Phase 3: Collection Layer

- Add crawler source registry. (Feed source registry with category, priority,
  polling interval, and request-delay metadata is in place.)
- Start with lightweight HTTP fetchers for a few sources. (RSS/Atom fetchers and
  scheduled-fetch CLI are in place. HTML listing adapter is in place for
  no-RSS source candidates, including optional detail-page deep fetch and main-text cleanup.)
- Add Scrapy project integration for larger crawling jobs.
- Prepare Airflow DAG wrappers after the first local pipeline is stable. (DAG
  wrapper is in `infra/airflow/dags`.)

## Phase 4: Storage Layer

- Add PostgreSQL repository interfaces and migrations. (Repository abstraction,
  JSONL implementation, PostgreSQL schema, PostgreSQL adapter, SQL-level listing,
  and database-backed feedback are in place.)
- Add object storage interface for raw pages and documents. (RawArchive protocol,
  local implementation, S3/MinIO adapter, and MinIO compose service are in place.)
- Add Neo4j writer for extracted entity and relation graphs. (Current MVP writes
  graph-shaped JSONL for later import.)

## Phase 4.1: Next Storage Work

- Add integration tests against a real PostgreSQL service in CI or local Docker Compose.
  (Local compose service and opt-in unittest are in place; CI wiring is still pending.)
- Add optional MinIO/S3 integration test that creates a bucket and writes a raw document.
- Add migration runner/versioning instead of applying raw SQL manually.
  (`migrate-postgres` records `schema_migrations` with the schema checksum.)

## Phase 5: Analysis Layer

- Add spaCy or Chinese NLP adapters for deterministic entity hints.
- Add LDA topic modeling pipeline.
- Add ARIMA/SARIMA time-series module for market indicators.
- Add risk scoring and event impact models.

## Phase 6: Operations

- Add structured logging, metrics, retries, and rate-limit controls.
- Track token usage, cost, latency, and extraction quality.
- Add human review queue and feedback loop.
- Add Docker Compose for local infrastructure. (PostgreSQL and MinIO services
  are in place.)
