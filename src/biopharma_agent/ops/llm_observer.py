"""LLM provider wrapper for metrics and logs."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from biopharma_agent.llm.base import LLMProvider
from biopharma_agent.llm.types import (
    EmbeddingRequest,
    EmbeddingResponse,
    LLMRequest,
    LLMResponse,
    StructuredOutputRequest,
)
from biopharma_agent.ops.metrics import InMemoryMetrics

logger = logging.getLogger(__name__)


@dataclass
class ObservedLLMProvider(LLMProvider):
    """Decorate any LLM provider with latency, usage, and failure metrics."""

    wrapped: LLMProvider
    metrics: InMemoryMetrics

    @property
    def provider_name(self) -> str:
        return self.wrapped.provider_name

    def chat(self, request: LLMRequest) -> LLMResponse:
        return self._measure("chat", lambda: self.wrapped.chat(request))

    def structured(self, request: StructuredOutputRequest) -> LLMResponse:
        return self._measure("structured", lambda: self.wrapped.structured(request))

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        return self._measure("embed", lambda: self.wrapped.embed(request))

    def _measure(self, operation: str, call):
        started = time.perf_counter()
        labels = {"provider": self.provider_name, "operation": operation}
        try:
            response = call()
        except Exception:
            self.metrics.increment("llm.errors", **labels)
            logger.exception("LLM request failed", extra={"extra": labels})
            raise

        elapsed = time.perf_counter() - started
        self.metrics.increment("llm.requests", **labels)
        self.metrics.observe("llm.latency_seconds", elapsed, **labels)
        usage = getattr(response, "usage", None)
        if usage and usage.total_tokens:
            self.metrics.increment("llm.tokens", usage.total_tokens, **labels)
        logger.info(
            "LLM request completed",
            extra={"extra": {**labels, "latency_seconds": round(elapsed, 4)}},
        )
        return response

