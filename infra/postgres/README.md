# PostgreSQL Storage

The default storage backend is local JSONL so the workbench can run without
infrastructure. Use PostgreSQL when you want idempotent updates, SQL-level
document listing, database-backed feedback, and a durable shared store.

## Setup

With Docker Compose:

```bash
docker compose up -d postgres
export BIOPHARMA_STORAGE_BACKEND=postgres
export BIOPHARMA_POSTGRES_DSN="postgresql://biopharma:biopharma@127.0.0.1:55432/biopharma_agent"
```

The compose service automatically applies `infra/postgres/schema.sql` to a new
database volume. To run the optional integration checks:

```bash
scripts/run_postgres_integration.sh
```

For the combined PostgreSQL and MinIO smoke used by CI:

```bash
scripts/run_storage_smoke.sh
```

Without Docker Compose:

```bash
createdb biopharma_agent
export BIOPHARMA_STORAGE_BACKEND=postgres
export BIOPHARMA_POSTGRES_DSN="postgresql://localhost:5432/biopharma_agent"
psql "$BIOPHARMA_POSTGRES_DSN" -f infra/postgres/schema.sql
```

The Python runtime needs `psycopg` when the PostgreSQL backend is selected:

```bash
python3 -m pip install "psycopg[binary]>=3"
```

The smoke scripts use `PYTHON` when it is set; otherwise they prefer the active
virtualenv, then `.venv/bin/python`, then `python3`.

JSONL remains available with:

```bash
export BIOPHARMA_STORAGE_BACKEND=jsonl
export BIOPHARMA_ANALYSIS_JSONL_PATH=data/processed/insights.jsonl
```

When PostgreSQL is enabled, `/api/documents` applies source, event type, risk,
keyword, sort, limit, and offset in SQL. `/api/feedback` reads and writes the
`feedback` table.
