"""PostgreSQL-backed human feedback repository."""

from __future__ import annotations

import importlib
import json
from typing import Any

from biopharma_agent.ops.feedback import FeedbackRecord, feedback_to_jsonable


class PostgresFeedbackRepository:
    """Store review decisions in the PostgreSQL feedback table."""

    def __init__(self, dsn: str, connect_timeout: int = 10) -> None:
        if not dsn:
            raise ValueError("PostgreSQL DSN is required")
        self.dsn = dsn
        self.connect_timeout = connect_timeout

    def append(self, record: FeedbackRecord) -> int:
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    insert into feedback (
                        document_id,
                        reviewer,
                        decision,
                        comment,
                        corrections,
                        created_at
                    )
                    values (%s, %s, %s, %s, %s::jsonb, %s)
                    returning id
                    """,
                    (
                        record.document_id,
                        record.reviewer,
                        record.decision,
                        record.comment,
                        json.dumps(record.corrections, ensure_ascii=False),
                        record.created_at,
                    ),
                )
                row_id = int(cursor.fetchone()[0])
            connection.commit()
        return row_id

    def list_records(self, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("select count(*) from feedback")
                total = int(cursor.fetchone()[0])
                cursor.execute(
                    """
                    select
                        document_id,
                        reviewer,
                        decision,
                        comment,
                        corrections,
                        created_at
                    from feedback
                    order by created_at desc, id desc
                    limit %s offset %s
                    """,
                    (limit, offset),
                )
                items = [_feedback_row(row) for row in cursor.fetchall()]
        return {
            "path": "postgres",
            "items": items,
            "count": len(items),
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total,
        }

    def _connect(self):
        psycopg = importlib.import_module("psycopg")
        return psycopg.connect(self.dsn, connect_timeout=self.connect_timeout)


def _feedback_row(row: tuple[Any, ...]) -> dict[str, Any]:
    document_id, reviewer, decision, comment, corrections, created_at = row
    payload = feedback_to_jsonable(
        FeedbackRecord(
            document_id=document_id or "",
            reviewer=reviewer or "",
            decision=decision or "",
            comment=comment or "",
            corrections=_decode_json(corrections),
            created_at=created_at,
        )
    )
    return payload


def _decode_json(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        decoded = json.loads(value)
        return decoded if isinstance(decoded, dict) else {}
    return {}
