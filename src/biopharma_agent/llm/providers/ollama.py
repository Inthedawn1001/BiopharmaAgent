"""Ollama local model provider adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from biopharma_agent.config import LLMSettings
from biopharma_agent.llm.base import LLMProvider
from biopharma_agent.llm.errors import LLMResponseError
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
class OllamaProvider(LLMProvider):
    """Adapter for local Ollama APIs."""

    settings: LLMSettings
    transport: JsonTransport = UrllibJsonTransport()
    provider_name: str = "ollama"

    def chat(self, request: LLMRequest) -> LLMResponse:
        raw = self.transport.post_json(
            f"{self.settings.base_url}/api/chat",
            self._payload(request),
            headers={},
            timeout=self.settings.timeout_seconds,
        )
        return self._parse_response(raw)

    def structured(self, request: StructuredOutputRequest) -> LLMResponse:
        payload = self._payload(
            LLMRequest(
                messages=request.messages,
                model=request.model,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                metadata=request.metadata,
            )
        )
        payload["format"] = request.json_schema
        raw = self.transport.post_json(
            f"{self.settings.base_url}/api/chat",
            payload,
            headers={},
            timeout=self.settings.timeout_seconds,
        )
        return self._parse_response(raw)

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        vectors: list[list[float]] = []
        raw_items: list[dict[str, Any]] = []
        for text in request.inputs:
            raw = self.transport.post_json(
                f"{self.settings.base_url}/api/embeddings",
                {"model": request.model or self.settings.model, "prompt": text},
                headers={},
                timeout=self.settings.timeout_seconds,
            )
            raw_items.append(raw)
            try:
                vectors.append(raw["embedding"])
            except KeyError as exc:
                raise LLMResponseError(f"Could not parse Ollama embedding response: {raw}") from exc
        return EmbeddingResponse(
            vectors=vectors,
            model=request.model or self.settings.model,
            provider=self.provider_name,
            raw={"items": raw_items},
        )

    def _payload(self, request: LLMRequest) -> dict[str, Any]:
        return {
            "model": request.model or self.settings.model,
            "messages": [message.to_dict() for message in request.messages],
            "stream": False,
            "options": {
                "temperature": (
                    self.settings.temperature
                    if request.temperature is None
                    else request.temperature
                ),
                "num_predict": request.max_tokens or self.settings.max_tokens,
            },
        }

    def _parse_response(self, raw: dict[str, Any]) -> LLMResponse:
        try:
            text = raw["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise LLMResponseError(f"Could not parse Ollama response: {raw}") from exc
        return LLMResponse(
            text=text,
            model=raw.get("model", self.settings.model),
            provider=self.provider_name,
            raw=raw,
            usage=LLMUsage(
                prompt_tokens=raw.get("prompt_eval_count"),
                completion_tokens=raw.get("eval_count"),
            ),
            finish_reason="stop" if raw.get("done") else None,
        )

