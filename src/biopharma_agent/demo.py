"""Demo data helpers for local workbench validation."""

from __future__ import annotations

from pathlib import Path

from biopharma_agent.contracts import ParsedDocument, PipelineResult, RawDocument, SourceRef
from biopharma_agent.ops.feedback import FeedbackRecord, LocalFeedbackRepository
from biopharma_agent.parsing.text import checksum_text
from biopharma_agent.storage.local import LocalAnalysisRepository

DEMO_TEXT = (
    "A biotech company announced Series B financing to advance a PD-1 combination "
    "therapy through phase 2 development and expand an autoimmune pipeline. The "
    "round included strategic and financial investors. Analysts noted that the "
    "financing may improve the company's research runway, while clinical failure, "
    "regulatory approval, and market competition remain key risks."
)


def seed_demo_data(
    output: Path | str = Path("data/processed/insights.jsonl"),
    feedback_output: Path | str = Path("data/feedback/reviews.jsonl"),
) -> dict[str, str]:
    """Write one deterministic document insight and one feedback record."""

    raw = RawDocument(
        source=SourceRef(name="demo", kind="manual"),
        document_id="demo-financing-pd1",
        title="Demo: PD-1 Combination Therapy Financing Event",
        raw_text=DEMO_TEXT,
    )
    parsed = ParsedDocument(
        raw=raw,
        text=DEMO_TEXT,
        checksum=checksum_text(DEMO_TEXT),
        language="en",
    )
    result = PipelineResult(
        document=parsed,
        model="demo",
        provider="deterministic",
        insight={
            "summary": "A biotech company completed Series B financing for a PD-1 phase 2 program.",
            "language": "en",
            "entities": [
                {
                    "name": "Demo Biotech",
                    "type": "company",
                    "normalized_name": "Demo Biotech",
                    "confidence": 0.8,
                    "evidence": "A biotech company announced Series B financing",
                },
                {
                    "name": "PD-1 combination therapy",
                    "type": "drug",
                    "normalized_name": "PD-1 combination therapy",
                    "confidence": 0.85,
                    "evidence": "advance a PD-1 combination therapy through phase 2",
                },
            ],
            "events": [
                {
                    "event_type": "financing",
                    "title": "Series B financing",
                    "date": "",
                    "companies": ["Demo Biotech"],
                    "amount": "",
                    "stage": "B",
                    "confidence": 0.9,
                    "evidence": "announced Series B financing",
                }
            ],
            "relations": [
                {
                    "subject": "Demo Biotech",
                    "predicate": "DEVELOPS",
                    "object": "PD-1 combination therapy",
                    "confidence": 0.8,
                    "evidence": "financing will advance the PD-1 combination therapy",
                }
            ],
            "risk_signals": [
                {
                    "risk_type": "clinical_and_regulatory",
                    "severity": "medium",
                    "description": "Clinical failure, regulatory approval, and competition remain key risks.",
                    "evidence": "clinical failure, regulatory approval, and market competition remain key risks",
                }
            ],
            "market_implications": ["The financing may improve the company's research runway."],
            "needs_human_review": False,
        },
    )
    insight_path = LocalAnalysisRepository(output).append(result)
    feedback_path = LocalFeedbackRepository(feedback_output).append(
        FeedbackRecord(
            document_id=raw.document_id,
            reviewer="demo-analyst",
            decision="accept",
            comment="Demo record for inbox and review workflow validation.",
        )
    )
    return {"insights": str(insight_path), "feedback": str(feedback_path)}
