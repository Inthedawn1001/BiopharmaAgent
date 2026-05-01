"""Local source health and incremental collection state."""

from __future__ import annotations

import json
import re
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

        collector = run.source.metadata.get("collector", "feed")
        category = run.source.metadata.get("category", "")
        enabled = bool(run.source.metadata.get("enabled", True))
        diagnosis = classify_source_error(
            run.error,
            collector=collector,
            status=run.status,
            enabled=enabled,
        )
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
            "collector": collector,
            "category": category,
            "enabled": enabled,
            "last_status": run.status,
            "last_started_at": _isoformat(run.started_at),
            "last_completed_at": _isoformat(run.completed_at),
            "last_error": run.error,
            **diagnosis,
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
        "backend": "jsonl",
        "generated_at": _isoformat(utc_now()),
        "items": items,
        "count": len(items),
        "summary": _summary(items),
    }


def source_state_summary(
    store: SourceStateStore,
    *,
    sources: list[SourceRef] | None = None,
    path: str = "",
    backend: str = "jsonl",
) -> dict[str, Any]:
    records_by_name = {record["source"]: record for record in store.list_records()}
    if sources is not None:
        for source in sources:
            records_by_name.setdefault(source.name, empty_source_state(source))
    items = [records_by_name[name] for name in sorted(records_by_name)]
    return {
        "path": path,
        "backend": backend,
        "generated_at": _isoformat(utc_now()),
        "items": items,
        "count": len(items),
        "summary": _summary(items),
    }


def empty_source_state(source: SourceRef) -> dict[str, Any]:
    collector = source.metadata.get("collector", "feed")
    enabled = bool(source.metadata.get("enabled", True))
    diagnosis = classify_source_error("", collector=collector, status="never_run", enabled=enabled)
    return {
        "source": source.name,
        "kind": source.kind,
        "collector": collector,
        "category": source.metadata.get("category", ""),
        "enabled": enabled,
        "last_status": "never_run",
        "last_started_at": "",
        "last_completed_at": "",
        "last_error": "",
        **diagnosis,
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
    total_selected = sum(int(item.get("last_selected", 0) or 0) for item in items)
    total_analyzed = sum(int(item.get("last_analyzed", 0) or 0) for item in items)
    total_skipped = sum(int(item.get("last_skipped_seen", 0) or 0) for item in items)
    total_seen = sum(int(item.get("seen_count", 0) or 0) for item in items)
    failure_types = _failure_type_counts(items)
    return {
        "success": success,
        "failed": failed,
        "never_run": never_run,
        "active": success + failed,
        "latest_completed_at": latest,
        "seen_documents": total_seen,
        "last_selected": total_selected,
        "last_analyzed": total_analyzed,
        "last_skipped_seen": total_skipped,
        "health_ratio": round(success / max(1, success + failed), 4),
        "failure_types": failure_types,
    }


def classify_source_error(
    error: str,
    *,
    collector: str = "",
    status: str = "",
    enabled: bool = True,
) -> dict[str, str]:
    """Classify a source run failure and provide an operator hint."""

    normalized = _normalize_error(error)
    status_value = str(status or "").lower()
    if not enabled:
        return _diagnosis(
            "disabled",
            "info",
            "Enable this source in source metadata before scheduling collection.",
        )
    if status_value != "failed" and not normalized:
        return _diagnosis("none", "info", "")
    if not normalized:
        return _diagnosis(
            "unknown",
            "error",
            "Check the run log for the source-specific traceback and retry with a small limit.",
        )

    collector_value = str(collector or "").lower()
    if _matches(normalized, _RATE_LIMIT_PATTERNS):
        return _diagnosis(
            "rate_limit",
            "warning",
            "Reduce request rate, lower the fetch limit, or retry after the provider window resets.",
        )
    if _matches(normalized, _STORAGE_PATTERNS):
        return _diagnosis(
            "storage",
            "error",
            "Check Postgres, object storage, disk space, and write permissions before retrying.",
        )
    if _matches(normalized, _LLM_PATTERNS) or (
        "provider" in normalized and collector_value not in {"feed", "html_listing"}
    ):
        return _diagnosis(
            "llm",
            "error",
            "Check the LLM provider, model name, base URL, API key, and quota configuration.",
        )
    if _matches(normalized, _AUTH_PATTERNS):
        return _diagnosis(
            "auth",
            "error",
            "Verify credentials, API keys, and access permissions for this source.",
        )
    if _matches(normalized, _NETWORK_PATTERNS):
        return _diagnosis(
            "network",
            "warning",
            "Retry after confirming DNS, TLS, proxy, and remote service availability.",
        )
    if _matches(normalized, _PARSER_PATTERNS):
        return _diagnosis(
            "parser",
            "warning",
            "Review the source adapter selectors or parser assumptions against the latest response.",
        )
    return _diagnosis(
        "unknown",
        "error",
        "Check the run log for the source-specific traceback and retry with a small limit.",
    )


def _document_ids(documents: list[RawDocument]) -> list[str]:
    return sorted({document.document_id for document in documents if document.document_id})


def _failure_type_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        failure_type = str(item.get("failure_type") or "none")
        if failure_type == "none":
            continue
        counts[failure_type] = counts.get(failure_type, 0) + 1
    return dict(sorted(counts.items()))


def _diagnosis(failure_type: str, severity: str, hint: str) -> dict[str, str]:
    return {
        "failure_type": failure_type,
        "failure_severity": severity,
        "remediation_hint": hint,
    }


def _matches(value: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(pattern.search(value) for pattern in patterns)


def _normalize_error(error: str) -> str:
    return re.sub(r"\s+", " ", str(error or "")).strip().lower()


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


_AUTH_PATTERNS = (
    re.compile(r"\b(401|403)\b"),
    re.compile(r"\bunauthori[sz]ed\b"),
    re.compile(r"\bforbidden\b"),
    re.compile(r"\bapi key\b"),
    re.compile(r"\binvalid key\b"),
    re.compile(r"\baccess denied\b"),
)
_RATE_LIMIT_PATTERNS = (
    re.compile(r"\b429\b"),
    re.compile(r"\brate[- ]?limit"),
    re.compile(r"\btoo many requests\b"),
    re.compile(r"\bquota exceeded\b"),
    re.compile(r"\bthrottl"),
)
_NETWORK_PATTERNS = (
    re.compile(r"\btimeout\b"),
    re.compile(r"\btimed out\b"),
    re.compile(r"\bdns\b"),
    re.compile(r"\bconnection (reset|refused|aborted|closed)\b"),
    re.compile(r"\bremote end closed\b"),
    re.compile(r"\bunreachable\b"),
    re.compile(r"\bssl\b"),
    re.compile(r"\btls\b"),
    re.compile(r"\bsocket\b"),
    re.compile(r"\burlopen\b"),
    re.compile(r"\bnetwork\b"),
)
_PARSER_PATTERNS = (
    re.compile(r"\bparse\b"),
    re.compile(r"\bjsondecode"),
    re.compile(r"\bxml\b"),
    re.compile(r"\brss\b"),
    re.compile(r"\bhtml extraction\b"),
    re.compile(r"\bunsupported feed\b"),
    re.compile(r"\bselector\b"),
    re.compile(r"\bunexpected format\b"),
    re.compile(r"\bcould not extract\b"),
    re.compile(r"\bmissing field\b"),
    re.compile(r"\bmalformed\b"),
    re.compile(r"\binvalid json\b"),
)
_LLM_PATTERNS = (
    re.compile(r"\bllm\b"),
    re.compile(r"\bopenai\b"),
    re.compile(r"\bdeepseek\b"),
    re.compile(r"\bmodel\b"),
    re.compile(r"\bchat completions?\b"),
    re.compile(r"\bcompletion\b"),
    re.compile(r"\bcontext length\b"),
    re.compile(r"\bprompt\b"),
    re.compile(r"\btoken\b"),
)
_STORAGE_PATTERNS = (
    re.compile(r"\bpostgres\b"),
    re.compile(r"\bpsycopg\b"),
    re.compile(r"\bdatabase\b"),
    re.compile(r"\bminio\b"),
    re.compile(r"\bs3\b"),
    re.compile(r"\bbucket\b"),
    re.compile(r"\bdisk\b"),
    re.compile(r"\bfile system\b"),
    re.compile(r"\bno space left\b"),
    re.compile(r"\bpermission denied\b"),
    re.compile(r"\barchive\b"),
    re.compile(r"\bobject store\b"),
)
