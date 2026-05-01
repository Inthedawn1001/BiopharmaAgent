"""Anthropic Claude provider adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from biopharma_agent.config import LLMSettings
from biopharma_agent.llm.base import LLMProvider
from biopharma_agent.llm.errors import LLMConfigurationError, LLMResponseError
from biopharma_agent.llm.http import JsonTransport, UrllibJsonTransport
from biopharma_agent.llm.types import (
    EmbeddingRequest,
    EmbeddingResponse,
    LLMRequest,
    LLMResponse,
    LLMUsage,
    StructuredOutputRequest,
)


@dataclass
class AnthropicProvider(LLMProvider):
    """Adapter for Anthropic Messages API."""

    settings: LLMSettings
    transport: JsonTransport = UrllibJsonTransport()
    provider_name: str = "anthropic"

    def chat(self, request: LLMRequest) -> LLMResponse:
        raw = self.transport.post_json(
            f"{self.settings.base_url}/v1/messages",
            self._payload(request),
            headers=self._headers(),
            timeout=self.settings.timeout_seconds,
        )
        return self._parse_response(raw)

    def structured(self, request: StructuredOutputRequest) -> LLMResponse:
        schema_instruction = (
            "Return only valid JSON matching this JSON Schema, with no markdown fences:\n"
            f"{request.json_schema}"
        )
        structured_messages = [
            *request.messages,
            type(request.messages[-1])(role="user", content=schema_instruction),
        ]
        raw = self.transport.post_json(
            f"{self.settings.base_url}/v1/messages",
            self._payload(
                LLMRequest(
                    messages=structured_messages,
                    model=request.model,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    metadata=request.metadata,
                )
            ),
            headers=self._headers(),
            timeout=self.settings.timeout_seconds,
        )
        return self._parse_response(raw)

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        raise LLMConfigurationError(
            "Anthropic embeddings are not implemented in this adapter. "
            "Use an OpenAI-compatible or Gemini embedding provider."
        )

    def _payload(self, request: LLMRequest) -> dict[str, Any]:
        system_parts = [message.content for message in request.messages if message.role == "system"]
        messages = [
            {"role": message.role, "content": message.content}
            for message in request.messages
            if message.role != "system"
        ]
        payload: dict[str, Any] = {
            "model": request.model or self.settings.model,
            "messages": messages,
            "max_tokens": request.max_tokens or self.settings.max_tokens,
            "temperature": (
                self.settings.temperature
                if request.temperature is None
                else request.temperature
            ),
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)
        return payload

    def _parse_response(self, raw: dict[str, Any]) -> LLMResponse:
        try:
            content = raw["content"]
            text = "".join(part.get("text", "") for part in content if part.get("type") == "text")
        except (KeyError, TypeError) as exc:
            raise LLMResponseError(f"Could not parse Anthropic response: {raw}") from exc
        return LLMResponse(
            text=text,
            model=raw.get("model", self.settings.model),
            provider=self.provider_name,
            raw=raw,
            usage=LLMUsage.from_mapping(raw.get("usage")),
            finish_reason=raw.get("stop_reason"),
        )

    def _headers(self) -> dict[str, str]:
        if not self.settings.api_key:
            raise LLMConfigurationError("BIOPHARMA_LLM_API_KEY is required for Anthropic.")
        return {
            "x-api-key": self.settings.api_key,
            "anthropic-version": "2023-06-01",
        }

