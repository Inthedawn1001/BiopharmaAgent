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

- Add crawler source registry. (Feed/source registry with category, priority,
  polling interval, request-delay metadata, and reusable source profiles is in place.)
- Start with lightweight HTTP fetchers for a few sources. (RSS/Atom, HTML
  listing, ASX announcement, and SEC submissions collectors are in place,
  including optional detail-page deep fetch and main-text cleanup.)
- Add Scrapy project integration for larger crawling jobs.
- Prepare Airflow DAG wrappers after the first local pipeline is stable. (DAG
  wrapper is in `infra/airflow/dags` and can run the full daily cycle.)

## Phase 4: Storage Layer

- Add PostgreSQL repository interfaces and migrations. (Repository abstraction,
  JSONL implementation, PostgreSQL schema, PostgreSQL adapter, SQL-level listing,
  and database-backed feedback are in place.)
- Add object storage interface for raw pages and documents. (RawArchive protocol,
  local implementation, S3/MinIO adapter, and MinIO compose service are in place.)
- Add Neo4j writer for extracted entity and relation graphs. (Graph-shaped JSONL
  and optional Neo4j writes are in place.)

## Phase 4.1: Next Storage Work

- Add integration tests against a real PostgreSQL service in CI or local Docker Compose.
  (Local compose service, opt-in unittest, and CI storage smoke are in place.)
- Add optional MinIO/S3 integration test that creates a bucket and writes a raw document.
  (MinIO smoke is in place and included in CI storage smoke.)
- Add migration runner/versioning instead of applying raw SQL manually.
  (`migrate-postgres` records `schema_migrations` with the schema checksum.)

## Phase 5: Analysis Layer

- Add spaCy or Chinese NLP adapters for deterministic entity hints.
- Add LDA topic modeling pipeline.
- Add ARIMA/SARIMA time-series module for market indicators.
- Add risk scoring and event impact models.

## Phase 6: Operations

- Add structured logging, metrics, retries, and rate-limit controls. (Structured
  logs, source request delays, source health state, run logs, and failure
  diagnosis are in place.)
- Track token usage, cost, latency, and extraction quality. (LLM observer
  metrics, document quality labels, source health reports, diagnostics, and a
  production quality gate are in place.)
- Add human review queue and feedback loop. (Feedback repository and workbench
  review flows are in place.)
- Add Docker Compose for local infrastructure. (PostgreSQL and MinIO services
  are in place, with storage, full-stack, and Airflow smoke scripts.)

## Production Readiness Focus

- The main daily productivity loop is implemented: collect prioritized sources,
  analyze with the configured LLM, update source health, generate a brief, and
  validate outputs with `quality-gate`.
- Remaining production-hardening work is mostly scale and governance: broader
  source expansion, Scrapy for high-volume crawling, richer deterministic NLP,
  topic/time-series models beyond the current keyword/time-series modules,
  managed secret storage, deployed observability, and access control.
