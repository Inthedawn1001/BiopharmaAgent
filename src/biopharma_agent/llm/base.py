"""Provider interface for all language model backends."""

from __future__ import annotations

from abc import ABC, abstractmethod

from biopharma_agent.llm.types import (
    EmbeddingRequest,
    EmbeddingResponse,
    LLMRequest,
    LLMResponse,
    StructuredOutputRequest,
)


class LLMProvider(ABC):
    """Minimal provider contract used by the rest of the agent."""

    provider_name: str

    @abstractmethod
    def chat(self, request: LLMRequest) -> LLMResponse:
        """Run a chat completion request."""

    @abstractmethod
    def structured(self, request: StructuredOutputRequest) -> LLMResponse:
        """Run a structured output request."""

    @abstractmethod
    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Create embeddings for one or more input strings."""

