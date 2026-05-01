"""OpenAI-compatible provider adapter."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from biopharma_agent.config import LLMSettings
from biopharma_agent.llm.base import LLMProvider
from biopharma_agent.llm.errors import LLMHTTPError, LLMResponseError
from biopharma_agent.llm.http import JsonTransport, UrllibJsonTransport
from biopharma_agent.llm.types import (
    ChatMessage,
    EmbeddingRequest,
    EmbeddingResponse,
    LLMRequest,
    LLMResponse,
    LLMUsage,
    StructuredOutputRequest,
)


@dataclass
class OpenAICompatibleProvider(LLMProvider):
    """Adapter for OpenAI-compatible chat and embedding APIs."""

    settings: LLMSettings
    transport: JsonTransport = UrllibJsonTransport()
    provider_name: str = "openai"

    def chat(self, request: LLMRequest) -> LLMResponse:
        payload = self._chat_payload(request)
        raw = self.transport.post_json(
            self._url(self.settings.chat_path or "/chat/completions"),
            payload,
            headers=self._headers(),
            timeout=self.settings.timeout_seconds,
        )
        return self._parse_chat_response(raw)

    def structured(self, request: StructuredOutputRequest) -> LLMResponse:
        try:
            raw = self.transport.post_json(
                self._url(self.settings.chat_path or "/chat/completions"),
                self._json_schema_payload(request),
                headers=self._headers(),
                timeout=self.settings.timeout_seconds,
            )
        except LLMHTTPError as exc:
            if not _looks_like_response_format_mismatch(str(exc)):
                raise
            raw = self.transport.post_json(
                self._url(self.settings.chat_path or "/chat/completions"),
                self._json_object_payload(request),
                headers=self._headers(),
                timeout=self.settings.timeout_seconds,
            )
        return self._parse_chat_response(raw)

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        payload = {
            "model": request.model or self.settings.model,
            "input": request.inputs,
        }
        raw = self.transport.post_json(
            self._url(self.settings.embedding_path or "/embeddings"),
            payload,
            headers=self._headers(),
            timeout=self.settings.timeout_seconds,
        )
        try:
            vectors = [item["embedding"] for item in raw["data"]]
        except (KeyError, TypeError) as exc:
            raise LLMResponseError(f"Could not parse embedding response: {raw}") from exc
        return EmbeddingResponse(
            vectors=vectors,
            model=raw.get("model", payload["model"]),
            provider=self.provider_name,
            raw=raw,
            usage=LLMUsage.from_mapping(raw.get("usage")),
        )

    def _chat_payload(self, request: LLMRequest) -> dict[str, Any]:
        return {
            "model": request.model or self.settings.model,
            "messages": [message.to_dict() for message in request.messages],
            "temperature": (
                self.settings.temperature
                if request.temperature is None
                else request.temperature
            ),
            "max_tokens": request.max_tokens or self.settings.max_tokens,
            "stream": request.stream,
        }

    def _json_schema_payload(self, request: StructuredOutputRequest) -> dict[str, Any]:
        payload = self._chat_payload(
            LLMRequest(
                messages=request.messages,
                model=request.model,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                metadata=request.metadata,
            )
        )
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": request.schema_name,
                "schema": request.json_schema,
                "strict": True,
            },
        }
        return payload

    def _json_object_payload(self, request: StructuredOutputRequest) -> dict[str, Any]:
        schema_instruction = (
            "Return only valid JSON. Do not include markdown fences. "
            "The JSON object must follow this JSON Schema:\n"
            f"{request.json_schema}"
        )
        messages = [
            *request.messages,
            ChatMessage(role="user", content=schema_instruction),
        ]
        payload = self._chat_payload(
            LLMRequest(
                messages=messages,
                model=request.model,
                temperature=request.temperature,
                max_tokens=request.max_tokens,
                metadata=request.metadata,
            )
        )
        payload["response_format"] = {"type": "json_object"}
        return payload

    def _parse_chat_response(self, raw: dict[str, Any]) -> LLMResponse:
        try:
            choice = raw["choices"][0]
            message = choice.get("message", {})
            text = message.get("content") or choice.get("text") or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMResponseError(f"Could not parse chat response: {raw}") from exc
        return LLMResponse(
            text=text,
            model=raw.get("model", self.settings.model),
            provider=self.provider_name,
            raw=raw,
            usage=LLMUsage.from_mapping(raw.get("usage")),
            finish_reason=choice.get("finish_reason"),
        )

    def _url(self, path: str) -> str:
        normalized_path = path if path.startswith("/") else f"/{path}"
        return f"{self.settings.base_url}{normalized_path}"

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.settings.api_key:
            headers["Authorization"] = f"Bearer {self.settings.api_key}"
        return headers


def _looks_like_response_format_mismatch(message: str) -> bool:
    lowered = message.lower()
    return "response_format" in lowered and (
        "unavailable" in lowered
        or "json_schema" in lowered
        or "must be" in lowered
        or "invalid_request" in lowered
    )
