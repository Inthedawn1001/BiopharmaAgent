"""Google Gemini provider adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

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
class GeminiProvider(LLMProvider):
    """Adapter for Gemini generateContent APIs."""

    settings: LLMSettings
    transport: JsonTransport = UrllibJsonTransport()
    provider_name: str = "gemini"

    def chat(self, request: LLMRequest) -> LLMResponse:
        raw = self.transport.post_json(
            self._model_url(request.model or self.settings.model, "generateContent"),
            self._payload(request),
            headers={},
            timeout=self.settings.timeout_seconds,
        )
        return self._parse_response(raw, request.model or self.settings.model)

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
        payload["generationConfig"]["responseMimeType"] = "application/json"
        payload["generationConfig"]["responseSchema"] = request.json_schema
        raw = self.transport.post_json(
            self._model_url(request.model or self.settings.model, "generateContent"),
            payload,
            headers={},
            timeout=self.settings.timeout_seconds,
        )
        return self._parse_response(raw, request.model or self.settings.model)

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        model = request.model or self.settings.model
        vectors: list[list[float]] = []
        raw_items: list[dict[str, Any]] = []
        for text in request.inputs:
            raw = self.transport.post_json(
                self._model_url(model, "embedContent"),
                {"content": {"parts": [{"text": text}]}},
                headers={},
                timeout=self.settings.timeout_seconds,
            )
            raw_items.append(raw)
            try:
                vectors.append(raw["embedding"]["values"])
            except (KeyError, TypeError) as exc:
                raise LLMResponseError(f"Could not parse Gemini embedding response: {raw}") from exc
        return EmbeddingResponse(
            vectors=vectors,
            model=model,
            provider=self.provider_name,
            raw={"items": raw_items},
        )

    def _payload(self, request: LLMRequest) -> dict[str, Any]:
        system_parts = [message.content for message in request.messages if message.role == "system"]
        contents: list[dict[str, Any]] = []
        for message in request.messages:
            if message.role == "system":
                continue
            role = "model" if message.role == "assistant" else "user"
            contents.append({"role": role, "parts": [{"text": message.content}]})

        payload: dict[str, Any] = {
            "contents": contents,
            "generationConfig": {
                "temperature": (
                    self.settings.temperature
                    if request.temperature is None
                    else request.temperature
                ),
                "maxOutputTokens": request.max_tokens or self.settings.max_tokens,
            },
        }
        if system_parts:
            payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
        return payload

    def _parse_response(self, raw: dict[str, Any], model: str) -> LLMResponse:
        try:
            parts = raw["candidates"][0]["content"]["parts"]
            text = "".join(part.get("text", "") for part in parts)
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMResponseError(f"Could not parse Gemini response: {raw}") from exc
        usage = raw.get("usageMetadata") or {}
        return LLMResponse(
            text=text,
            model=model,
            provider=self.provider_name,
            raw=raw,
            usage=LLMUsage(
                prompt_tokens=usage.get("promptTokenCount"),
                completion_tokens=usage.get("candidatesTokenCount"),
                total_tokens=usage.get("totalTokenCount"),
            ),
            finish_reason=raw.get("candidates", [{}])[0].get("finishReason"),
        )

    def _model_url(self, model: str, action: str) -> str:
        if not self.settings.api_key:
            raise LLMConfigurationError("BIOPHARMA_LLM_API_KEY is required for Gemini.")
        query = urlencode({"key": self.settings.api_key})
        return f"{self.settings.base_url}/models/{model}:{action}?{query}"

