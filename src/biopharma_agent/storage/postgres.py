"""PostgreSQL repository for production-grade document storage."""

from __future__ import annotations

import importlib
import json
from dataclasses import asdict
from datetime import datetime
from typing import Any

from biopharma_agent.contracts import PipelineResult
from biopharma_agent.storage.repository import (
    DocumentFilters,
    DocumentListResult,
    build_document_detail,
    document_quality,
)


class PostgresAnalysisRepository:
    """Persist analyzed documents into PostgreSQL using a small DB-API surface."""

    def __init__(self, dsn: str, connect_timeout: int = 10) -> None:
        if not dsn:
            raise ValueError("PostgreSQL DSN is required")
        self.dsn = dsn
        self.connect_timeout = connect_timeout

    def append(self, result: PipelineResult) -> None:
        payload = _to_jsonable(asdict(result))
        document = payload.get("document", {})
        raw = document.get("raw", {})
        source = raw.get("source", {})
        insight = payload.get("insight", {})
        event = _first_dict(insight.get("events", []))
        risk = _highest_risk(insight.get("risk_signals", []))
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into sources (name, kind, url, metadata)
                    values (%s, %s, %s, %s::jsonb)
                    on conflict (name) do update set
                        kind = excluded.kind,
                        url = excluded.url,
                        metadata = sources.metadata || excluded.metadata,
                        updated_at = now()
                    """,
                    (
                        source.get("name") or "",
                        source.get("kind") or "",
                        source.get("url"),
                        _json(source.get("metadata", {})),
                    ),
                )
                cursor.execute(
                    """
                    insert into documents (
                        document_id,
                        source_name,
                        checksum,
                        title,
                        url,
                        language,
                        published_at,
                        collected_at,
                        raw_uri,
                        text,
                        metadata,
                        payload
                    )
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
                    on conflict (source_name, document_id) do update set
                        checksum = excluded.checksum,
                        title = excluded.title,
                        url = excluded.url,
                        language = excluded.language,
                        published_at = excluded.published_at,
                        collected_at = excluded.collected_at,
                        raw_uri = excluded.raw_uri,
                        text = excluded.text,
                        metadata = excluded.metadata,
                        payload = excluded.payload,
                        updated_at = now()
                    """,
                    (
                        raw.get("document_id") or document.get("checksum") or "",
                        source.get("name") or "",
                        document.get("checksum") or "",
                        raw.get("title"),
                        raw.get("url"),
                        document.get("language"),
                        document.get("published_at"),
                        raw.get("collected_at"),
                        raw.get("raw_uri"),
                        document.get("text") or "",
                        _json(document.get("metadata", {})),
                        _json(document),
                    ),
                )
                cursor.execute(
                    """
                    insert into insights (
                        source_name,
                        document_id,
                        provider,
                        model,
                        summary,
                        event_type,
                        risk,
                        needs_human_review,
                        payload,
                        pipeline_payload
                    )
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)
                    on conflict (source_name, document_id, provider, model) do update set
                        summary = excluded.summary,
                        event_type = excluded.event_type,
                        risk = excluded.risk,
                        needs_human_review = excluded.needs_human_review,
                        payload = excluded.payload,
                        pipeline_payload = excluded.pipeline_payload,
                        updated_at = now()
                    returning id
                    """,
                    (
                        source.get("name") or "",
                        raw.get("document_id") or document.get("checksum") or "",
                        payload.get("provider") or "",
                        payload.get("model") or "",
                        insight.get("summary") or "",
                        event.get("event_type") or "",
                        risk,
                        bool(insight.get("needs_human_review")),
                        _json(insight),
                        _json(payload),
                    ),
                )
                insight_id = cursor.fetchone()[0]
                self._replace_child_rows(cursor, insight_id, insight)
            connection.commit()

    def list_records(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    select pipeline_payload
                    from insights
                    order by created_at asc, id asc
                    limit %s offset %s
                    """,
                    (limit, offset),
                )
                return [_decode_json(row[0]) for row in cursor.fetchall()]

    def list_documents(self, filters: DocumentFilters) -> DocumentListResult:
        normalized = filters.normalized()
        where_sql, params = _document_where_clause(normalized)
        order_sql = _document_order_clause(normalized.sort_by, normalized.sort_direction)
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select count(*) from insights")
                total = int(cursor.fetchone()[0])
                cursor.execute(f"select count(*) from {_document_from_sql()} {where_sql}", params)
                filtered_total = int(cursor.fetchone()[0])
                cursor.execute(
                    f"""
                    select
                        i.pipeline_payload,
                        d.document_id,
                        d.title,
                        d.url,
                        s.name,
                        s.kind,
                        i.created_at,
                        i.provider,
                        i.model,
                        i.summary,
                        i.event_type,
                        i.risk,
                        i.needs_human_review
                    from {_document_from_sql()}
                    {where_sql}
                    {order_sql}
                    limit %s offset %s
                    """,
                    [*params, normalized.limit, normalized.offset],
                )
                rows = [_document_row_from_sql(row) for row in cursor.fetchall()]
                facets = _document_facets_from_postgres(cursor)
        return DocumentListResult(
            items=rows,
            count=len(rows),
            total=total,
            filtered_total=filtered_total,
            limit=normalized.limit,
            offset=normalized.offset,
            filters=normalized.to_dict(),
            facets=facets,
            path="postgres",
            has_more=normalized.offset + normalized.limit < filtered_total,
        )

    def get_document(self, document_id: str, source: str = "") -> dict[str, Any] | None:
        if not document_id.strip():
            return None
        clauses = ["i.document_id = %s"]
        params: list[Any] = [document_id.strip()]
        if source.strip():
            clauses.append("i.source_name = %s")
            params.append(source.strip())
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    select i.pipeline_payload
                    from {_document_from_sql()}
                    where {" and ".join(clauses)}
                    order by i.created_at desc, i.id desc
                    limit 1
                    """,
                    params,
                )
                row = cursor.fetchone()
        if not row:
            return None
        return build_document_detail(_decode_json(row[0]))

    def _connect(self):
        psycopg = importlib.import_module("psycopg")
        return psycopg.connect(self.dsn, connect_timeout=self.connect_timeout)

    def _replace_child_rows(self, cursor: Any, insight_id: int, insight: dict[str, Any]) -> None:
        for table in [
            "insight_entities",
            "insight_events",
            "insight_relations",
            "risk_signals",
        ]:
            cursor.execute(f"delete from {table} where insight_id = %s", (insight_id,))

        for entity in _dicts(insight.get("entities")):
            cursor.execute(
                """
                insert into insight_entities (
                    insight_id,
                    name,
                    normalized_name,
                    entity_type,
                    confidence,
                    evidence,
                    payload
                )
                values (%s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    insight_id,
                    entity.get("name") or entity.get("normalized_name") or "",
                    entity.get("normalized_name"),
                    entity.get("type"),
                    _number_or_none(entity.get("confidence")),
                    entity.get("evidence"),
                    _json(entity),
                ),
            )

        for event in _dicts(insight.get("events")):
            cursor.execute(
                """
                insert into insight_events (
                    insight_id,
                    event_type,
                    title,
                    event_date,
                    companies,
                    amount,
                    stage,
                    confidence,
                    evidence,
                    payload
                )
                values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    insight_id,
                    event.get("event_type"),
                    event.get("title"),
                    event.get("date"),
                    [str(item) for item in event.get("companies", [])]
                    if isinstance(event.get("companies"), list)
                    else [],
                    event.get("amount"),
                    event.get("stage"),
                    _number_or_none(event.get("confidence")),
                    event.get("evidence"),
                    _json(event),
                ),
            )

        for relation in _dicts(insight.get("relations")):
            cursor.execute(
                """
                insert into insight_relations (
                    insight_id,
                    subject,
                    predicate,
                    object,
                    confidence,
                    evidence,
                    payload
                )
                values (%s, %s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    insight_id,
                    relation.get("subject") or "",
                    relation.get("predicate") or "",
                    relation.get("object") or "",
                    _number_or_none(relation.get("confidence")),
                    relation.get("evidence"),
                    _json(relation),
                ),
            )

        for risk in _dicts(insight.get("risk_signals")):
            cursor.execute(
                """
                insert into risk_signals (
                    insight_id,
                    risk_type,
                    severity,
                    rationale,
                    evidence,
                    payload
                )
                values (%s, %s, %s, %s, %s, %s::jsonb)
                """,
                (
                    insight_id,
                    risk.get("risk_type"),
                    risk.get("severity"),
                    risk.get("rationale"),
                    risk.get("evidence"),
                    _json(risk),
                ),
            )


def _json(value: Any) -> str:
    return json.dumps(_to_jsonable(value), ensure_ascii=False)


def _document_from_sql() -> str:
    return """
    insights i
    join documents d
      on d.source_name = i.source_name
     and d.document_id = i.document_id
    join sources s
      on s.name = i.source_name
    """


def _document_where_clause(filters: DocumentFilters) -> tuple[str, list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if filters.source:
        clauses.append("s.name = %s")
        params.append(filters.source)
    if filters.event_type:
        clauses.append("i.event_type = %s")
        params.append(filters.event_type)
    if filters.risk:
        clauses.append("i.risk = %s")
        params.append(filters.risk)
    if filters.query:
        clauses.append(
            """
            (
                d.title ilike %s
                or s.name ilike %s
                or i.summary ilike %s
                or i.event_type ilike %s
                or i.risk ilike %s
            )
            """
        )
        pattern = f"%{filters.query}%"
        params.extend([pattern, pattern, pattern, pattern, pattern])
    if not clauses:
        return "", params
    return "where " + " and ".join(clauses), params


def _document_order_clause(sort_by: str, direction: str) -> str:
    columns = {
        "created_at": "i.created_at",
        "source": "s.name",
        "event_type": "i.event_type",
        "risk": "i.risk",
    }
    column = columns.get(sort_by, "i.created_at")
    sql_direction = "desc" if direction == "desc" else "asc"
    return f"order by {column} {sql_direction}, i.id {sql_direction}"


def _document_row_from_sql(row: tuple[Any, ...]) -> dict[str, Any]:
    (
        pipeline_payload,
        document_id,
        title,
        url,
        source_name,
        source_kind,
        created_at,
        provider,
        model,
        summary,
        event_type,
        risk,
        needs_human_review,
    ) = row
    record = _decode_json(pipeline_payload)
    event_title = ""
    insight = record.get("insight") if isinstance(record.get("insight"), dict) else {}
    events = insight.get("events") if isinstance(insight.get("events"), list) else []
    if events and isinstance(events[0], dict):
        event_title = str(events[0].get("title") or "")
    quality = document_quality(record)
    return {
        "id": document_id or "",
        "title": title or summary or "Untitled",
        "source": source_name or "",
        "source_kind": source_kind or "",
        "url": url or "",
        "created_at": created_at.isoformat() if hasattr(created_at, "isoformat") else str(created_at or ""),
        "provider": provider or "",
        "model": model or "",
        "summary": summary or "",
        "event_type": event_type or "",
        "event_title": event_title or event_type or "",
        "risk": risk or "",
        "needs_human_review": bool(needs_human_review),
        "body_quality": quality["label"],
        "text_length": quality["text_length"],
        "word_count": quality["word_count"],
        "extraction_method": quality["extraction_method"],
        "html_cleaned": quality["html_cleaned"],
        "record": record,
    }


def _document_facets_from_postgres(cursor: Any) -> dict[str, list[str]]:
    cursor.execute("select name from sources where name <> '' order by name")
    sources = [row[0] for row in cursor.fetchall()]
    cursor.execute("select distinct event_type from insights where event_type <> '' order by event_type")
    event_types = [row[0] for row in cursor.fetchall()]
    cursor.execute("select distinct risk from insights where risk <> '' order by risk")
    risks = [row[0] for row in cursor.fetchall()]
    return {"sources": sources, "event_types": event_types, "risks": risks}


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    return value


def _decode_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        decoded = json.loads(value)
        return decoded if isinstance(decoded, dict) else {}
    return {}


def _first_dict(values: Any) -> dict[str, Any]:
    if isinstance(values, list) and values and isinstance(values[0], dict):
        return values[0]
    return {}


def _dicts(values: Any) -> list[dict[str, Any]]:
    if not isinstance(values, list):
        return []
    return [value for value in values if isinstance(value, dict)]


def _number_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _highest_risk(risks: Any) -> str:
    order = {"high": 3, "medium": 2, "low": 1, "unknown": 0}
    best = ""
    best_score = -1
    if not isinstance(risks, list):
        return best
    for risk in risks:
        if not isinstance(risk, dict):
            continue
        severity = str(risk.get("severity", "")).lower()
        score = order.get(severity, -1)
        if score > best_score:
            best = severity
            best_score = score
    return best
