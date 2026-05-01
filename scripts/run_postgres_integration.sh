#!/usr/bin/env bash
set -euo pipefail

export BIOPHARMA_POSTGRES_DSN="${BIOPHARMA_POSTGRES_DSN:-postgresql://biopharma:biopharma@127.0.0.1:55432/biopharma_agent}"
export BIOPHARMA_RUN_POSTGRES_TESTS=1
export PYTHONPATH="src${PYTHONPATH:+:${PYTHONPATH}}"

if [[ -z "${PYTHON:-}" ]]; then
  if [[ -n "${VIRTUAL_ENV:-}" && -x "${VIRTUAL_ENV}/bin/python" ]]; then
    PYTHON="${VIRTUAL_ENV}/bin/python"
  elif [[ -x ".venv/bin/python" ]]; then
    PYTHON=".venv/bin/python"
  else
    PYTHON="python3"
  fi
fi

"${PYTHON}" -m biopharma_agent.cli migrate-postgres
"${PYTHON}" -m unittest tests.test_postgres_integration
"${PYTHON}" scripts/postgres_smoke.py
