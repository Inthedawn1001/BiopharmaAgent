"""LLM-assisted biopharma document analysis pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from biopharma_agent.analysis.json_utils import parse_json_object
from biopharma_agent.analysis.prompts import BIOPHARMA_SYSTEM_PROMPT, insight_user_prompt
from biopharma_agent.analysis.schemas import DOCUMENT_INSIGHT_SCHEMA
from biopharma_agent.llm.base import LLMProvider
from biopharma_agent.llm.types import ChatMessage, LLMRequest, StructuredOutputRequest


@dataclass
class BiopharmaAnalysisPipeline:
    """High-level analysis workflow powered by an injected LLM provider."""

    llm: LLMProvider
    default_max_chars: int = 20000

    def summarize(self, text: str, max_chars: int | None = None) -> str:
        bounded_text = self._bounded_text(text, max_chars)
        response = self.llm.chat(
            LLMRequest(
                messages=[
                    ChatMessage(role="system", content=BIOPHARMA_SYSTEM_PROMPT),
                    ChatMessage(
                        role="user",
                        content=(
                            "Summarize this document in 5 concise bullets. "
                            "Keep factual claims tied to the input.\n\n"
                            f"{bounded_text}"
                        ),
                    ),
                ],
                temperature=0.1,
            )
        )
        return response.text.strip()

    def extract_insight(self, text: str, max_chars: int | None = None) -> dict[str, Any]:
        bounded_text = self._bounded_text(text, max_chars)
        response = self.llm.structured(
            StructuredOutputRequest(
                messages=[
                    ChatMessage(role="system", content=BIOPHARMA_SYSTEM_PROMPT),
                    ChatMessage(role="user", content=insight_user_prompt(bounded_text)),
                ],
                json_schema=DOCUMENT_INSIGHT_SCHEMA,
                schema_name="biopharma_document_insight",
                temperature=0.1,
            )
        )
        return parse_json_object(response.text)

    def classify_event(self, text: str) -> str:
        insight = self.extract_insight(text)
        events = insight.get("events") or []
        if not events:
            return "other"
        first = events[0]
        return str(first.get("event_type") or "other")

    def _bounded_text(self, text: str, max_chars: int | None = None) -> str:
        limit = max_chars or self.default_max_chars
        if len(text) <= limit:
            return text
        return text[:limit] + "\n\n[TRUNCATED]"

