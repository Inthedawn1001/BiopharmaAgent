"""LLM provider abstractions and adapters."""

from biopharma_agent.llm.base import LLMProvider
from biopharma_agent.llm.factory import create_llm_provider
from biopharma_agent.llm.types import (
    ChatMessage,
    EmbeddingRequest,
    EmbeddingResponse,
    LLMRequest,
    LLMResponse,
    StructuredOutputRequest,
)

__all__ = [
    "ChatMessage",
    "EmbeddingRequest",
    "EmbeddingResponse",
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
    "StructuredOutputRequest",
    "create_llm_provider",
]

