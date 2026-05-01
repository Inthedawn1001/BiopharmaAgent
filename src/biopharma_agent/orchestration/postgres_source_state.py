"""PostgreSQL-backed source health and incremental state."""

from __future__ import annotations

import importlib
import json
from datetime import datetime
from typing import Any

from biopharma_agent.contracts import RawDocument, SourceRef, utc_now
from biopharma_agent.orchestration.source_state import SourceRunUpdate


class PostgresSourceStateStore:
    """Persist source state in PostgreSQL."""

    def __init__(self, dsn: str, connect_timeout: int = 10) -> None:
        if not dsn:
            raise ValueError("PostgreSQL DSN is required")
        self.dsn = dsn
        self.connect_timeout = connect_timeout

    def list_records(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select
                        source_name,
                        kind,
                        collector,
                        category,
                        enabled,
                        last_status,
                        last_started_at,
                        last_completed_at,
                        last_error,
                        last_fetched,
                        last_selected,
                        last_analyzed,
                        last_skipped_seen,
                        last_document_ids,
                        seen_document_ids,
                        consecutive_failures,
                        updated_at
                    from source_states
                    order by source_name
                    """
                )
                return [_record_from_row(row) for row in cursor.fetchall()]

    def get_record(self, source_name: str) -> dict[str, Any] | None:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select
                        source_name,
                        kind,
                        collector,
                        category,
                        enabled,
                        last_status,
                        last_started_at,
                        last_completed_at,
                        last_error,
                        last_fetched,
                        last_selected,
                        last_analyzed,
                        last_skipped_seen,
                        last_document_ids,
                        seen_document_ids,
                        consecutive_failures,
                        updated_at
                    from source_states
                    where source_name = %s
                    """,
                    (source_name,),
                )
                row = cursor.fetchone()
        return _record_from_row(row) if row else None

    def seen_document_ids(self, source_name: str) -> set[str]:
        record = self.get_record(source_name) or {}
        values = record.get("seen_document_ids", [])
        return {str(value) for value in values if str(value)} if isinstance(values, list) else set()

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
        previous = self.get_record(run.source.name) or {}
        previous_seen = _string_list(previous.get("seen_document_ids", []))
        document_ids = sorted({document.document_id for document in run.documents or [] if document.document_id})
        seen_document_ids = sorted({*previous_seen, *document_ids})
        summary = run.summary or {}
        consecutive_failures = int(previous.get("consecutive_failures", 0) or 0)
        consecutive_failures = 0 if run.status == "success" else consecutive_failures + 1
        updated_at = utc_now()
        payload = {
            "last_document_ids": document_ids,
            "seen_count": len(seen_document_ids),
            "summary": summary,
        }
        params = (
            run.source.name,
            run.source.kind,
            run.source.metadata.get("collector", "feed"),
            run.source.metadata.get("category", ""),
            bool(run.source.metadata.get("enabled", True)),
            run.status,
            run.started_at,
            run.completed_at,
            run.error,
            int(summary.get("fetched", 0) or 0),
            int(summary.get("selected", 0) or 0),
            int(summary.get("analyzed", 0) or 0),
            int(summary.get("skipped_seen", 0) or 0),
            document_ids,
            seen_document_ids,
            consecutive_failures,
            json.dumps(payload, ensure_ascii=False),
            updated_at,
        )
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(_UPSERT_SQL, params)
            connection.commit()
        return self.get_record(run.source.name) or {}

    def _connect(self) -> Any:
        psycopg = importlib.import_module("psycopg")
        return psycopg.connect(self.dsn, connect_timeout=self.connect_timeout)


_UPSERT_SQL = """
insert into source_states (
    source_name,
    kind,
    collector,
    category,
    enabled,
    last_status,
    last_started_at,
    last_completed_at,
    last_error,
    last_fetched,
    last_selected,
    last_analyzed,
    last_skipped_seen,
    last_document_ids,
    seen_document_ids,
    consecutive_failures,
    payload,
    updated_at
)
values (
    %s,
    %s,
    %s,
    %s,
    %s,
    %s,
    %s,
    %s,
    %s,
    %s,
    %s,
    %s,
    %s,
    %s,
    %s,
    %s,
    %s::jsonb,
    %s
)
on conflict (source_name) do update set
    kind = excluded.kind,
    collector = excluded.collector,
    category = excluded.category,
    enabled = excluded.enabled,
    last_status = excluded.last_status,
    last_started_at = excluded.last_started_at,
    last_completed_at = excluded.last_completed_at,
    last_error = excluded.last_error,
    last_fetched = excluded.last_fetched,
    last_selected = excluded.last_selected,
    last_analyzed = excluded.last_analyzed,
    last_skipped_seen = excluded.last_skipped_seen,
    last_document_ids = excluded.last_document_ids,
    seen_document_ids = excluded.seen_document_ids,
    consecutive_failures = excluded.consecutive_failures,
    payload = excluded.payload,
    updated_at = excluded.updated_at
"""


def _record_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    (
        source_name,
        kind,
        collector,
        category,
        enabled,
        last_status,
        last_started_at,
        last_completed_at,
        last_error,
        last_fetched,
        last_selected,
        last_analyzed,
        last_skipped_seen,
        last_document_ids,
        seen_document_ids,
        consecutive_failures,
        updated_at,
    ) = row
    seen = _string_list(seen_document_ids)
    return {
        "source": source_name or "",
        "kind": kind or "",
        "collector": collector or "feed",
        "category": category or "",
        "enabled": bool(enabled),
        "last_status": last_status or "never_run",
        "last_started_at": _iso_or_empty(last_started_at),
        "last_completed_at": _iso_or_empty(last_completed_at),
        "last_error": last_error or "",
        "last_fetched": int(last_fetched or 0),
        "last_selected": int(last_selected or 0),
        "last_analyzed": int(last_analyzed or 0),
        "last_skipped_seen": int(last_skipped_seen or 0),
        "last_document_ids": _string_list(last_document_ids),
        "seen_document_ids": seen,
        "seen_count": len(seen),
        "consecutive_failures": int(consecutive_failures or 0),
        "updated_at": _iso_or_empty(updated_at),
    }


def _string_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, tuple):
        return [str(item) for item in value if str(item)]
    if isinstance(value, str) and value:
        return [value]
    return []


def _iso_or_empty(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else str(value or "")
