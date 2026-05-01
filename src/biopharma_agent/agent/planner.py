"""LLM-assisted task routing for incoming documents."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from biopharma_agent.analysis.json_utils import parse_json_object
from biopharma_agent.llm.base import LLMProvider
from biopharma_agent.llm.types import ChatMessage, StructuredOutputRequest

ROUTING_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "document_type": {
            "type": "string",
            "enum": [
                "news",
                "exchange_announcement",
                "regulatory_policy",
                "research_report",
                "clinical_trial",
                "financial_statement",
                "other",
            ],
        },
        "priority": {"type": "string", "enum": ["low", "normal", "high", "urgent"]},
        "recommended_steps": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [
                    "summarize",
                    "extract_entities",
                    "extract_events",
                    "extract_relations",
                    "update_knowledge_graph",
                    "run_market_impact_analysis",
                    "run_risk_review",
                    "human_review",
                    "archive_only",
                ],
            },
        },
        "reason": {"type": "string"},
    },
    "required": ["document_type", "priority", "recommended_steps", "reason"],
}


@dataclass
class LLMTaskPlanner:
    """Ask an LLM which downstream processing steps should run for a document."""

    llm: LLMProvider

    def plan(self, text: str) -> dict[str, Any]:
        response = self.llm.structured(
            StructuredOutputRequest(
                messages=[
                    ChatMessage(
                        role="system",
                        content=(
                            "You route biopharma and capital-market documents to processing "
                            "steps. Use only the given text and return compact JSON."
                        ),
                    ),
                    ChatMessage(
                        role="user",
                        content=(
                            "Decide the document type, urgency, and downstream processing "
                            f"steps for this text:\n\n{text[:12000]}"
                        ),
                    ),
                ],
                json_schema=ROUTING_SCHEMA,
                schema_name="document_routing_plan",
                temperature=0,
            )
        )
        return parse_json_object(response.text)

