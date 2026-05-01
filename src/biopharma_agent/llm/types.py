"""Provider-neutral LLM request and response models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    content: str
    name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.name:
            payload["name"] = self.name
        return payload


@dataclass(frozen=True)
class LLMRequest:
    messages: list[ChatMessage]
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    stream: bool = False


@dataclass(frozen=True)
class StructuredOutputRequest:
    messages: list[ChatMessage]
    json_schema: dict[str, Any]
    schema_name: str = "structured_output"
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class LLMUsage:
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None

    @classmethod
    def from_mapping(cls, value: dict[str, Any] | None) -> "LLMUsage":
        if not value:
            return cls()
        return cls(
            prompt_tokens=value.get("prompt_tokens") or value.get("input_tokens"),
            completion_tokens=value.get("completion_tokens") or value.get("output_tokens"),
            total_tokens=value.get("total_tokens"),
        )


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    provider: str
    raw: dict[str, Any] = field(default_factory=dict)
    usage: LLMUsage = field(default_factory=LLMUsage)
    finish_reason: str | None = None


@dataclass(frozen=True)
class EmbeddingRequest:
    inputs: list[str]
    model: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class EmbeddingResponse:
    vectors: list[list[float]]
    model: str
    provider: str
    raw: dict[str, Any] = field(default_factory=dict)
    usage: LLMUsage = field(default_factory=LLMUsage)

