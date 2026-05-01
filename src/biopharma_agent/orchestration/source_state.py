"""Local source health and incremental collection state."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

from biopharma_agent.contracts import RawDocument, SourceRef, utc_now


@dataclass(frozen=True)
class SourceRunUpdate:
    """A single source collection outcome used to update local state."""

    source: SourceRef
    status: str
    started_at: datetime
    completed_at: datetime
    summary: dict[str, Any] | None = None
    documents: list[RawDocument] | None = None
    error: str = ""


class SourceStateStore(Protocol):
    def list_records(self) -> list[dict[str, Any]]:
        """List persisted source state records."""

    def get_record(self, source_name: str) -> dict[str, Any] | None:
        """Return one source state record by source name."""

    def seen_document_ids(self, source_name: str) -> set[str]:
        """Return seen document IDs for one source."""

    def record_success(
        self,
        source: SourceRef,
        *,
        started_at: datetime,
        completed_at: datetime,
        summary: dict[str, Any],
        documents: list[RawDocument],
    ) -> dict[str, Any]:
        """Record a successful source run."""

    def record_failure(
        self,
        source: SourceRef,
        *,
        started_at: datetime,
        completed_at: datetime,
        error: str,
        summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Record a failed source run."""


class LocalSourceStateStore:
    """Persist source health and seen document IDs in a small JSON file."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def list_records(self) -> list[dict[str, Any]]:
        records = self._load()["sources"]
        return [dict(records[name]) for name in sorted(records)]

    def get_record(self, source_name: str) -> dict[str, Any] | None:
        record = self._load()["sources"].get(source_name)
        return dict(record) if isinstance(record, dict) else None

    def seen_document_ids(self, source_name: str) -> set[str]:
        record = self.get_record(source_name) or {}
        values = record.get("seen_document_ids", [])
        if not isinstance(values, list):
            return set()
        return {str(value) for value in values if str(value)}

    def record_success(
        self,
        source: SourceRef,
        *,
        started_at: datetime,
        completed_at: datetime,
        summary: dict[str, Any],
        documents: list[RawDocument],
    ) -> dict[str, Any]:
        return self.update(
            SourceRunUpdate(
                source=source,
                status="success",
                started_at=started_at,
                completed_at=completed_at,
                summary=summary,
                documents=documents,
            )
        )

    def record_failure(
        self,
        source: SourceRef,
        *,
        started_at: datetime,
        completed_at: datetime,
        error: str,
        summary: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.update(
            SourceRunUpdate(
                source=source,
                status="failed",
                started_at=started_at,
                completed_at=completed_at,
                summary=summary,
                documents=[],
                error=error,
            )
        )

    def update(self, run: SourceRunUpdate) -> dict[str, Any]:
        payload = self._load()
        records: dict[str, Any] = payload["sources"]
        previous = records.get(run.source.name, {})
        if not isinstance(previous, dict):
            previous = {}

        previous_seen = _string_list(previous.get("seen_document_ids", []))
        document_ids = _document_ids(run.documents or [])
        seen_document_ids = sorted({*previous_seen, *document_ids})
        summary = run.summary or {}
        consecutive_failures = int(previous.get("consecutive_failures", 0) or 0)
        if run.status == "success":
            consecutive_failures = 0
        else:
            consecutive_failures += 1

        record = {
            "source": run.source.name,
            "kind": run.source.kind,
            "collector": run.source.metadata.get("collector", "feed"),
            "category": run.source.metadata.get("category", ""),
            "enabled": run.source.metadata.get("enabled", True),
            "last_status": run.status,
            "last_started_at": _isoformat(run.started_at),
            "last_completed_at": _isoformat(run.completed_at),
            "last_error": run.error,
            "last_fetched": int(summary.get("fetched", 0) or 0),
            "last_selected": int(summary.get("selected", 0) or 0),
            "last_analyzed": int(summary.get("analyzed", 0) or 0),
            "last_skipped_seen": int(summary.get("skipped_seen", 0) or 0),
            "last_document_ids": document_ids,
            "seen_document_ids": seen_document_ids,
            "seen_count": len(seen_document_ids),
            "consecutive_failures": consecutive_failures,
            "updated_at": _isoformat(utc_now()),
        }
        records[run.source.name] = record
        payload["updated_at"] = record["updated_at"]
        self._save(payload)
        return dict(record)

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "updated_at": "", "sources": {}}
        decoded = json.loads(self.path.read_text(encoding="utf-8") or "{}")
        if not isinstance(decoded, dict):
            raise ValueError(f"source state file must contain a JSON object: {self.path}")
        sources = decoded.get("sources", {})
        if not isinstance(sources, dict):
            raise ValueError(f"source state file has invalid sources object: {self.path}")
        return {
            "version": int(decoded.get("version", 1) or 1),
            "updated_at": str(decoded.get("updated_at", "")),
            "sources": sources,
        }

    def _save(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_suffix(f"{self.path.suffix}.tmp")
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temp_path.replace(self.path)


def state_summary(path: Path | str, sources: list[SourceRef] | None = None) -> dict[str, Any]:
    """Return source state, optionally merged with configured sources."""

    store = LocalSourceStateStore(path)
    records_by_name = {record["source"]: record for record in store.list_records()}
    if sources is not None:
        for source in sources:
            records_by_name.setdefault(source.name, empty_source_state(source))
    items = [records_by_name[name] for name in sorted(records_by_name)]
    return {
        "path": str(Path(path)),
        "items": items,
        "count": len(items),
        "summary": _summary(items),
    }


def source_state_summary(
    store: SourceStateStore,
    *,
    sources: list[SourceRef] | None = None,
    path: str = "",
) -> dict[str, Any]:
    records_by_name = {record["source"]: record for record in store.list_records()}
    if sources is not None:
        for source in sources:
            records_by_name.setdefault(source.name, empty_source_state(source))
    items = [records_by_name[name] for name in sorted(records_by_name)]
    return {
        "path": path,
        "items": items,
        "count": len(items),
        "summary": _summary(items),
    }


def empty_source_state(source: SourceRef) -> dict[str, Any]:
    return {
        "source": source.name,
        "kind": source.kind,
        "collector": source.metadata.get("collector", "feed"),
        "category": source.metadata.get("category", ""),
        "enabled": source.metadata.get("enabled", True),
        "last_status": "never_run",
        "last_started_at": "",
        "last_completed_at": "",
        "last_error": "",
        "last_fetched": 0,
        "last_selected": 0,
        "last_analyzed": 0,
        "last_skipped_seen": 0,
        "last_document_ids": [],
        "seen_document_ids": [],
        "seen_count": 0,
        "consecutive_failures": 0,
        "updated_at": "",
    }


def _summary(items: list[dict[str, Any]]) -> dict[str, Any]:
    success = sum(1 for item in items if item.get("last_status") == "success")
    failed = sum(1 for item in items if item.get("last_status") == "failed")
    never_run = sum(1 for item in items if item.get("last_status") == "never_run")
    latest = max((str(item.get("last_completed_at", "")) for item in items), default="")
    return {
        "success": success,
        "failed": failed,
        "never_run": never_run,
        "latest_completed_at": latest,
        "seen_documents": sum(int(item.get("seen_count", 0) or 0) for item in items),
    }


def _document_ids(documents: list[RawDocument]) -> list[str]:
    return sorted({document.document_id for document in documents if document.document_id})


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, str) and value:
        return [value]
    return []


def _isoformat(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()
