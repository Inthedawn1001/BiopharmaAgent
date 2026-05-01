"""Deterministic provider for infrastructure smoke tests."""

from __future__ import annotations

import json
from dataclasses import dataclass

from biopharma_agent.llm.base import LLMProvider
from biopharma_agent.llm.types import (
    EmbeddingRequest,
    EmbeddingResponse,
    LLMRequest,
    LLMResponse,
    StructuredOutputRequest,
)


@dataclass
class SmokeProvider(LLMProvider):
    """Return schema-compatible responses without external network calls."""

    provider_name: str = "smoke"
    model: str = "smoke-model"

    def chat(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            text="ok",
            model=request.model or self.model,
            provider=self.provider_name,
        )

    def structured(self, request: StructuredOutputRequest) -> LLMResponse:
        text = _request_text(request)
        title = _compact_title(text)
        payload = {
            "summary": title,
            "language": "en",
            "entities": [],
            "events": [
                {
                    "event_type": (
                        "policy" if "FDA" in text or "regulatory" in text.lower() else "other"
                    ),
                    "title": title,
                    "date": "",
                    "companies": [],
                    "amount": "",
                    "stage": "",
                    "confidence": 0.5,
                    "evidence": title,
                }
            ],
            "relations": [],
            "risk_signals": [],
            "market_implications": [
                "Smoke analysis confirmed the document reached the analysis pipeline."
            ],
            "needs_human_review": True,
        }
        return LLMResponse(
            text=json.dumps(payload),
            model=request.model or self.model,
            provider=self.provider_name,
        )

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        return EmbeddingResponse(
            vectors=[[0.0] for _ in request.inputs],
            model=request.model or self.model,
            provider=self.provider_name,
        )


def _request_text(request: StructuredOutputRequest) -> str:
    if not request.messages:
        return ""
    return request.messages[-1].content


def _compact_title(text: str) -> str:
    normalized = " ".join(text.split())
    if not normalized:
        return "Smoke analysis result"
    return normalized[:180]
