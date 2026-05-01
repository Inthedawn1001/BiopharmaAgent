"""Factory for creating configured LLM providers."""

from __future__ import annotations

from biopharma_agent.config import LLMSettings
from biopharma_agent.llm.base import LLMProvider
from biopharma_agent.llm.errors import LLMConfigurationError
from biopharma_agent.llm.http import JsonTransport
from biopharma_agent.llm.providers import (
    AnthropicProvider,
    GeminiProvider,
    OllamaProvider,
    OpenAICompatibleProvider,
    SmokeProvider,
)


def create_llm_provider(
    settings: LLMSettings,
    transport: JsonTransport | None = None,
) -> LLMProvider:
    """Create an LLM provider from settings."""

    provider = settings.provider.lower()
    kwargs = {"settings": settings}
    if transport is not None:
        kwargs["transport"] = transport

    if provider == "openai":
        return OpenAICompatibleProvider(**kwargs, provider_name="openai")
    if provider == "custom":
        return OpenAICompatibleProvider(**kwargs, provider_name="custom")
    if provider == "anthropic":
        return AnthropicProvider(**kwargs)
    if provider == "gemini":
        return GeminiProvider(**kwargs)
    if provider == "ollama":
        return OllamaProvider(**kwargs)
    if provider == "smoke":
        return SmokeProvider(model=settings.model or "smoke-model")

    raise LLMConfigurationError(
        f"Unsupported LLM provider '{settings.provider}'. "
        "Expected one of: openai, custom, anthropic, gemini, ollama, smoke."
    )
