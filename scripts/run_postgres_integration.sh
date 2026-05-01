#!/usr/bin/env bash
set -euo pipefail

export BIOPHARMA_POSTGRES_DSN="${BIOPHARMA_POSTGRES_DSN:-postgresql://biopharma:biopharma@127.0.0.1:55432/biopharma_agent}"
export BIOPHARMA_RUN_POSTGRES_TESTS=1
export PYTHONPATH="src${PYTHONPATH:+:${PYTHONPATH}}"

python3 -m biopharma_agent.cli migrate-postgres
python3 -m unittest tests.test_postgres_integration
python3 scripts/postgres_smoke.py
