"""Repository contracts and query helpers for analyzed documents."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from biopharma_agent.contracts import PipelineResult


@dataclass(frozen=True)
class DocumentFilters:
    """Filters shared by local JSONL and database-backed document queries."""

    limit: int = 50
    offset: int = 0
    source: str = ""
    event_type: str = ""
    risk: str = ""
    query: str = ""
    sort_by: str = "created_at"
    sort_direction: str = "asc"

    def normalized(self) -> "DocumentFilters":
        limit = max(1, min(int(self.limit), 500))
        offset = max(0, int(self.offset))
        sort_by = self.sort_by if self.sort_by in {"created_at", "source", "risk", "event_type"} else "created_at"
        direction = "desc" if self.sort_direction.lower() == "desc" else "asc"
        return DocumentFilters(
            limit=limit,
            offset=offset,
            source=self.source.strip(),
            event_type=self.event_type.strip(),
            risk=self.risk.strip().lower(),
            query=self.query.strip(),
            sort_by=sort_by,
            sort_direction=direction,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "limit": self.limit,
            "offset": self.offset,
            "source": self.source,
            "event_type": self.event_type,
            "risk": self.risk,
            "query": self.query,
            "sort_by": self.sort_by,
            "sort_direction": self.sort_direction,
        }


@dataclass(frozen=True)
class DocumentListResult:
    """A paged list of flattened document rows for API and UI consumers."""

    items: list[dict[str, Any]]
    count: int
    total: int
    filtered_total: int
    limit: int
    offset: int
    filters: dict[str, Any]
    facets: dict[str, list[str]]
    path: str | None = None
    has_more: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "items": self.items,
            "count": self.count,
            "total": self.total,
            "filtered_total": self.filtered_total,
            "limit": self.limit,
            "offset": self.offset,
            "filters": self.filters,
            "facets": self.facets,
            "has_more": self.has_more,
        }
        if self.path is not None:
            payload["path"] = self.path
        return payload


class AnalysisRepository(Protocol):
    """Storage boundary for analyzed pipeline results."""

    def append(self, result: PipelineResult) -> object:
        """Persist or update one pipeline result."""

    def list_records(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """Return raw pipeline-result dictionaries."""

    def list_documents(self, filters: DocumentFilters) -> DocumentListResult:
        """Return flattened document rows with facets and pagination metadata."""

    def get_document(self, document_id: str, source: str = "") -> dict[str, Any] | None:
        """Return one document detail payload by source/document id."""


def query_documents_from_records(
    records: list[dict[str, Any]],
    filters: DocumentFilters,
    path: str | None = None,
) -> DocumentListResult:
    normalized = filters.normalized()
    rows = [_document_row(item) for item in records]
    filtered = [
        row
        for row in rows
        if _matches_filter(
            row,
            source=normalized.source,
            event_type=normalized.event_type,
            risk=normalized.risk,
            query=normalized.query,
        )
    ]
    sorted_rows = _sort_rows(filtered, normalized.sort_by, normalized.sort_direction)
    page = sorted_rows[normalized.offset : normalized.offset + normalized.limit]
    return DocumentListResult(
        path=path,
        items=page,
        count=len(page),
        total=len(rows),
        filtered_total=len(filtered),
        limit=normalized.limit,
        offset=normalized.offset,
        filters=normalized.to_dict(),
        facets=_document_facets(rows),
        has_more=normalized.offset + normalized.limit < len(filtered),
    )


def pipeline_record_key(record: dict[str, Any]) -> str:
    """Stable idempotency key for one stored analysis result."""

    document = record.get("document") if isinstance(record.get("document"), dict) else {}
    raw = document.get("raw") if isinstance(document.get("raw"), dict) else {}
    source = raw.get("source") if isinstance(raw.get("source"), dict) else {}
    parts = [
        source.get("name") or "",
        raw.get("document_id") or "",
        document.get("checksum") or "",
        record.get("provider") or "",
        record.get("model") or "",
    ]
    return "|".join(str(part) for part in parts)


def find_document_detail(
    records: list[dict[str, Any]],
    document_id: str,
    source: str = "",
) -> dict[str, Any] | None:
    """Find and expand a stored pipeline record into a UI-friendly detail payload."""

    normalized_id = document_id.strip()
    normalized_source = source.strip()
    if not normalized_id:
        return None
    for record in reversed(records):
        row = _document_row(record)
        if row["id"] != normalized_id:
            continue
        if normalized_source and row["source"] != normalized_source:
            continue
        return build_document_detail(record)
    return None


def build_document_detail(record: dict[str, Any]) -> dict[str, Any]:
    """Create a compact document detail object with text, insight, and quality metrics."""

    row = _document_row(record)
    document = record.get("document") if isinstance(record.get("document"), dict) else {}
    raw = document.get("raw") if isinstance(document.get("raw"), dict) else {}
    text = str(document.get("text") or raw.get("raw_text") or "")
    document_metadata = (
        document.get("metadata") if isinstance(document.get("metadata"), dict) else {}
    )
    raw_metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    insight = record.get("insight") if isinstance(record.get("insight"), dict) else {}
    return {
        "row": {key: value for key, value in row.items() if key != "record"},
        "document": {
            "id": row["id"],
            "title": row["title"],
            "source": row["source"],
            "source_kind": row["source_kind"],
            "url": row["url"],
            "text": text,
            "text_preview": text[:5000],
            "language": document.get("language") or "",
            "checksum": document.get("checksum") or "",
            "published_at": document.get("published_at") or raw_metadata.get("published_at") or "",
            "raw_uri": raw.get("raw_uri") or "",
            "metadata": document_metadata,
            "raw_metadata": raw_metadata,
        },
        "insight": insight,
        "provider": record.get("provider") or "",
        "model": record.get("model") or "",
        "created_at": record.get("created_at") or "",
        "quality": document_quality(record),
        "record": record,
    }


def document_quality(record: dict[str, Any]) -> dict[str, Any]:
    """Summarize body extraction quality without provider-specific assumptions."""

    document = record.get("document") if isinstance(record.get("document"), dict) else {}
    raw = document.get("raw") if isinstance(document.get("raw"), dict) else {}
    document_metadata = (
        document.get("metadata") if isinstance(document.get("metadata"), dict) else {}
    )
    raw_metadata = raw.get("metadata") if isinstance(raw.get("metadata"), dict) else {}
    text = str(document.get("text") or raw.get("raw_text") or "")
    stripped = text.strip()
    text_length = len(stripped)
    word_count = len(re.findall(r"\w+", stripped))
    line_count = len([line for line in stripped.splitlines() if line.strip()])
    parser = str(document_metadata.get("parser") or "")
    extraction_method = str(
        document_metadata.get("extraction_method")
        or raw_metadata.get("html_extraction_method")
        or parser
    )
    extraction_score = _float_or_zero(
        document_metadata.get("extraction_score") or raw_metadata.get("html_extraction_score")
    )
    original_html_length = _int_or_zero(raw_metadata.get("original_html_length"))
    clean_ratio = round(text_length / original_html_length, 4) if original_html_length else None
    html_cleaned = bool(raw_metadata.get("html_cleaned"))
    flags: list[str] = []
    if html_cleaned:
        flags.append("html_cleaned")
    if extraction_method:
        flags.append(f"method:{extraction_method}")
    if text_length < 120:
        flags.append("very_short_text")
    elif text_length < 350:
        flags.append("short_text")
    if clean_ratio is not None and clean_ratio < 0.02:
        flags.append("low_html_to_text_ratio")

    if text_length >= 1200:
        label = "strong"
    elif text_length >= 350:
        label = "usable"
    elif text_length >= 120:
        label = "short"
    else:
        label = "weak"

    return {
        "label": label,
        "text_length": text_length,
        "word_count": word_count,
        "line_count": line_count,
        "parser": parser,
        "extraction_method": extraction_method,
        "extraction_score": extraction_score,
        "html_cleaned": html_cleaned,
        "original_html_length": original_html_length,
        "clean_ratio": clean_ratio,
        "flags": flags,
    }


def _document_row(record: dict[str, Any]) -> dict[str, Any]:
    document = record.get("document") if isinstance(record.get("document"), dict) else {}
    raw = document.get("raw") if isinstance(document.get("raw"), dict) else {}
    source = raw.get("source") if isinstance(raw.get("source"), dict) else {}
    insight = record.get("insight") if isinstance(record.get("insight"), dict) else {}
    events = insight.get("events") if isinstance(insight.get("events"), list) else []
    risks = insight.get("risk_signals") if isinstance(insight.get("risk_signals"), list) else []
    first_event = events[0] if events and isinstance(events[0], dict) else {}
    highest_risk = _highest_risk(risks)
    quality = document_quality(record)
    return {
        "id": raw.get("document_id") or document.get("checksum") or "",
        "title": raw.get("title") or insight.get("summary") or "Untitled",
        "source": source.get("name") or "",
        "source_kind": source.get("kind") or "",
        "url": raw.get("url") or "",
        "created_at": record.get("created_at") or "",
        "provider": record.get("provider") or "",
        "model": record.get("model") or "",
        "summary": insight.get("summary") or "",
        "event_type": first_event.get("event_type") or "",
        "event_title": first_event.get("title") or "",
        "risk": highest_risk,
        "needs_human_review": bool(insight.get("needs_human_review")),
        "body_quality": quality["label"],
        "text_length": quality["text_length"],
        "word_count": quality["word_count"],
        "extraction_method": quality["extraction_method"],
        "html_cleaned": quality["html_cleaned"],
        "record": record,
    }


def _highest_risk(risks: list[Any]) -> str:
    order = {"high": 3, "medium": 2, "low": 1, "unknown": 0}
    best = ""
    best_score = -1
    for risk in risks:
        if not isinstance(risk, dict):
            continue
        severity = str(risk.get("severity", "")).lower()
        score = order.get(severity, -1)
        if score > best_score:
            best = severity
            best_score = score
    return best


def _matches_filter(
    row: dict[str, Any],
    source: str,
    event_type: str,
    risk: str,
    query: str,
) -> bool:
    if source and row["source"] != source:
        return False
    if event_type and row["event_type"] != event_type:
        return False
    if risk and row["risk"] != risk:
        return False
    if query:
        haystack = " ".join(
            str(row.get(field, ""))
            for field in [
                "id",
                "title",
                "source",
                "summary",
                "event_type",
                "event_title",
                "risk",
                "url",
                "model",
                "provider",
            ]
        ).lower()
        if query.lower() not in haystack:
            return False
    return True


def _document_facets(rows: list[dict[str, Any]]) -> dict[str, list[str]]:
    return {
        "sources": sorted({row["source"] for row in rows if row["source"]}),
        "event_types": sorted({row["event_type"] for row in rows if row["event_type"]}),
        "risks": sorted({row["risk"] for row in rows if row["risk"]}),
    }


def _sort_rows(rows: list[dict[str, Any]], sort_by: str, direction: str) -> list[dict[str, Any]]:
    reverse = direction == "desc"
    return sorted(rows, key=lambda row: str(row.get(sort_by, "")), reverse=reverse)


def _float_or_zero(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _int_or_zero(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
