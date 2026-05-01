"""Human feedback storage for model output review."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class FeedbackRecord:
    document_id: str
    reviewer: str
    decision: str
    comment: str = ""
    corrections: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class FeedbackRepository(Protocol):
    """Storage boundary for human review records."""

    def append(self, record: FeedbackRecord) -> object:
        """Persist one feedback record."""

    def list_records(self, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        """Return a paginated list of feedback records."""


class LocalFeedbackRepository:
    """Append human review records to JSONL."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def append(self, record: FeedbackRecord) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(feedback_to_jsonable(record), ensure_ascii=False) + "\n")
        return self.path

    def list_records(self, limit: int = 50, offset: int = 0) -> dict[str, Any]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        if not self.path.exists():
            return {
                "path": str(self.path),
                "items": [],
                "count": 0,
                "total": 0,
                "limit": limit,
                "offset": offset,
                "has_more": False,
            }
        records: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            decoded = json.loads(line)
            if isinstance(decoded, dict):
                records.append(decoded)
        page = records[offset : offset + limit]
        return {
            "path": str(self.path),
            "items": page,
            "count": len(page),
            "total": len(records),
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < len(records),
        }


def feedback_to_jsonable(record: FeedbackRecord) -> dict[str, Any]:
    payload = asdict(record)
    payload["created_at"] = record.created_at.isoformat()
    return payload
