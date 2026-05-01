"""Smoke-test PostgreSQL storage with one synthetic pipeline result."""

from __future__ import annotations

import os
from pathlib import Path

from biopharma_agent.contracts import ParsedDocument, PipelineResult, RawDocument, SourceRef
from biopharma_agent.ops.feedback import FeedbackRecord
from biopharma_agent.ops.postgres_feedback import PostgresFeedbackRepository
from biopharma_agent.parsing.text import checksum_text
from biopharma_agent.storage.postgres import PostgresAnalysisRepository
from biopharma_agent.storage.repository import DocumentFilters


SMOKE_TEXT = (
    "PostgreSQL smoke record: a biopharma company announced financing and regulatory risk."
)


def main() -> int:
    dsn = os.getenv(
        "BIOPHARMA_POSTGRES_DSN",
        "postgresql://biopharma:biopharma@127.0.0.1:55432/biopharma_agent",
    )
    analysis_repository = PostgresAnalysisRepository(dsn)
    feedback_repository = PostgresFeedbackRepository(dsn)

    raw = RawDocument(
        source=SourceRef(name="postgres_smoke", kind="integration", url="local://postgres-smoke"),
        document_id="postgres-smoke-doc",
        title="PostgreSQL Smoke Document",
        raw_text=SMOKE_TEXT,
    )
    parsed = ParsedDocument(
        raw=raw,
        text=SMOKE_TEXT,
        checksum=checksum_text(SMOKE_TEXT),
        language="en",
    )
    result = PipelineResult(
        document=parsed,
        model="smoke-model",
        provider="smoke-provider",
        insight={
            "summary": "A synthetic biopharma financing record with regulatory risk.",
            "language": "en",
            "entities": [
                {
                    "name": "Smoke Biopharma",
                    "type": "company",
                    "normalized_name": "Smoke Biopharma",
                    "confidence": 0.99,
                    "evidence": "biopharma company announced financing",
                }
            ],
            "events": [
                {
                    "event_type": "financing",
                    "title": "Synthetic financing",
                    "companies": ["Smoke Biopharma"],
                    "confidence": 0.99,
                    "evidence": "announced financing",
                }
            ],
            "relations": [],
            "risk_signals": [
                {
                    "risk_type": "regulatory",
                    "severity": "medium",
                    "rationale": "Synthetic regulatory risk for smoke testing.",
                    "evidence": "regulatory risk",
                }
            ],
            "market_implications": ["Synthetic capital-market implication."],
            "needs_human_review": True,
        },
    )
    analysis_repository.append(result)
    feedback_repository.append(
        FeedbackRecord(
            document_id=raw.document_id,
            reviewer="postgres-smoke",
            decision="accept",
            comment="PostgreSQL smoke test feedback.",
        )
    )
    documents = analysis_repository.list_documents(
        DocumentFilters(source="postgres_smoke", event_type="financing", risk="medium", limit=5)
    )
    feedback = feedback_repository.list_records(limit=5)
    print(
        {
            "dsn": _redact_dsn(dsn),
            "documents": documents.to_dict(),
            "feedback_count": feedback["count"],
        }
    )
    return 0


def _redact_dsn(dsn: str) -> str:
    if "@" not in dsn or "://" not in dsn:
        return dsn
    scheme, rest = dsn.split("://", 1)
    return f"{scheme}://***@{rest.split('@', 1)[1]}"


if __name__ == "__main__":
    raise SystemExit(main())
