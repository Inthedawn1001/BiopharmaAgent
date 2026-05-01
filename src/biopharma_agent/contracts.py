"""Stable contracts shared between collection, parsing, storage, and analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class SourceRef:
    """A logical source such as a news site, exchange, regulator, or database."""

    name: str
    kind: str
    url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RawDocument:
    """A collected raw document before deterministic parsing."""

    source: SourceRef
    document_id: str
    collected_at: datetime = field(default_factory=utc_now)
    url: str | None = None
    title: str | None = None
    raw_text: str | None = None
    raw_uri: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ParsedDocument:
    """Normalized text plus source metadata ready for analysis."""

    raw: RawDocument
    text: str
    checksum: str
    language: str | None = None
    published_at: datetime | None = None
    authors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PipelineResult:
    """Result object returned by an analysis pipeline."""

    document: ParsedDocument
    insight: dict[str, Any]
    model: str
    provider: str
    created_at: datetime = field(default_factory=utc_now)

