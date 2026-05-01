"""Demo data helpers for local workbench validation."""

from __future__ import annotations

from pathlib import Path

from biopharma_agent.contracts import ParsedDocument, PipelineResult, RawDocument, SourceRef
from biopharma_agent.ops.feedback import FeedbackRecord, LocalFeedbackRepository
from biopharma_agent.parsing.text import checksum_text
from biopharma_agent.storage.local import LocalAnalysisRepository

DEMO_TEXT = (
    "某生物技术公司宣布完成B轮融资，募集资金将用于推进PD-1联合疗法的临床II期研究，"
    "并扩展自身免疫疾病管线。公司表示，本轮融资由产业基金和多家投资机构共同参与。"
    "分析人士认为，该事件可能改善公司研发资金状况，但临床失败、监管审批和市场竞争仍是主要风险。"
)


def seed_demo_data(
    output: Path | str = Path("data/processed/insights.jsonl"),
    feedback_output: Path | str = Path("data/feedback/reviews.jsonl"),
) -> dict[str, str]:
    """Write one deterministic document insight and one feedback record."""

    raw = RawDocument(
        source=SourceRef(name="demo", kind="manual"),
        document_id="demo-financing-pd1",
        title="Demo: PD-1 联合疗法融资事件",
        raw_text=DEMO_TEXT,
    )
    parsed = ParsedDocument(
        raw=raw,
        text=DEMO_TEXT,
        checksum=checksum_text(DEMO_TEXT),
        language="zh",
    )
    result = PipelineResult(
        document=parsed,
        model="demo",
        provider="deterministic",
        insight={
            "summary": "某生物技术公司完成B轮融资，资金将用于PD-1联合疗法临床II期研究。",
            "language": "zh",
            "entities": [
                {
                    "name": "某生物技术公司",
                    "type": "company",
                    "normalized_name": "某生物技术公司",
                    "confidence": 0.8,
                    "evidence": "某生物技术公司宣布完成B轮融资",
                },
                {
                    "name": "PD-1联合疗法",
                    "type": "drug",
                    "normalized_name": "PD-1联合疗法",
                    "confidence": 0.85,
                    "evidence": "推进PD-1联合疗法的临床II期研究",
                },
            ],
            "events": [
                {
                    "event_type": "financing",
                    "title": "B轮融资",
                    "date": "",
                    "companies": ["某生物技术公司"],
                    "amount": "",
                    "stage": "B",
                    "confidence": 0.9,
                    "evidence": "宣布完成B轮融资",
                }
            ],
            "relations": [
                {
                    "subject": "某生物技术公司",
                    "predicate": "DEVELOPS",
                    "object": "PD-1联合疗法",
                    "confidence": 0.8,
                    "evidence": "募集资金将用于推进PD-1联合疗法",
                }
            ],
            "risk_signals": [
                {
                    "risk_type": "clinical_and_regulatory",
                    "severity": "medium",
                    "description": "临床失败、监管审批和市场竞争仍是主要风险。",
                    "evidence": "临床失败、监管审批和市场竞争仍是主要风险",
                }
            ],
            "market_implications": ["融资可能改善研发资金状况。"],
            "needs_human_review": False,
        },
    )
    insight_path = LocalAnalysisRepository(output).append(result)
    feedback_path = LocalFeedbackRepository(feedback_output).append(
        FeedbackRecord(
            document_id=raw.document_id,
            reviewer="demo-analyst",
            decision="accept",
            comment="演示记录：抽取结果可用于收件箱和复核流测试。",
        )
    )
    return {"insights": str(insight_path), "feedback": str(feedback_path)}

