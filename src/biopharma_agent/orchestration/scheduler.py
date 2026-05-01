"""Lightweight recurring job runner for local and cron-friendly operation."""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class JobRunRecord:
    """One scheduled job attempt."""

    job_name: str
    run_id: str
    status: str
    started_at: datetime
    completed_at: datetime
    duration_seconds: float
    result: Any = None
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class LocalRunLog:
    """Append scheduled run records to JSONL."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def append(self, record: JobRunRecord) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(_to_jsonable(asdict(record)), ensure_ascii=False) + "\n")
        return self.path

    def list_records(self, limit: int = 50) -> list[dict[str, Any]]:
        return self.list_records_page(limit=limit)["items"]

    def list_records_page(self, limit: int = 50, offset: int = 0) -> dict[str, Any]:
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
                "summary": _run_summary([]),
            }
        lines = self.path.read_text(encoding="utf-8").splitlines()
        records: list[dict[str, Any]] = []
        for line in lines:
            if not line.strip():
                continue
            decoded = json.loads(line)
            if isinstance(decoded, dict):
                records.append(decoded)
        ordered = list(reversed(records))
        page = ordered[offset : offset + limit]
        return {
            "path": str(self.path),
            "items": page,
            "count": len(page),
            "total": len(records),
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < len(records),
            "summary": _run_summary(records),
        }


class RecurringRunner:
    """Run a callable once or repeatedly while recording structured status."""

    def __init__(
        self,
        run_log: LocalRunLog,
        *,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.run_log = run_log
        self.sleep = sleep
        self.clock = clock

    def run_once(
        self,
        job_name: str,
        job: Callable[[], Any],
        *,
        metadata: dict[str, Any] | None = None,
    ) -> JobRunRecord:
        run_id = str(uuid4())
        started_at = self.clock()
        try:
            result = job()
            completed_at = self.clock()
            record = JobRunRecord(
                job_name=job_name,
                run_id=run_id,
                status="success",
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=_duration_seconds(started_at, completed_at),
                result=result,
                metadata=metadata or {},
            )
        except Exception as exc:
            completed_at = self.clock()
            record = JobRunRecord(
                job_name=job_name,
                run_id=run_id,
                status="failed",
                started_at=started_at,
                completed_at=completed_at,
                duration_seconds=_duration_seconds(started_at, completed_at),
                error=str(exc),
                metadata=metadata or {},
            )
        self.run_log.append(record)
        return record

    def run_forever(
        self,
        job_name: str,
        job: Callable[[], Any],
        *,
        interval_seconds: float,
        max_runs: int | None = None,
        stop_on_error: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> list[JobRunRecord]:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        if max_runs is not None and max_runs <= 0:
            raise ValueError("max_runs must be positive when set")

        records: list[JobRunRecord] = []
        while max_runs is None or len(records) < max_runs:
            record = self.run_once(job_name, job, metadata=metadata)
            records.append(record)
            if stop_on_error and record.status == "failed":
                break
            if max_runs is not None and len(records) >= max_runs:
                break
            self.sleep(interval_seconds)
        return records


def _duration_seconds(started_at: datetime, completed_at: datetime) -> float:
    return max(0.0, (completed_at - started_at).total_seconds())


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    return value


def _run_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    success_count = sum(1 for record in records if record.get("status") == "success")
    failed_count = sum(1 for record in records if record.get("status") == "failed")
    latest = records[-1] if records else {}
    result_rows: list[dict[str, Any]] = []
    for record in records:
        result = record.get("result")
        if not isinstance(result, list):
            continue
        result_rows.extend(item for item in result if isinstance(item, dict))
    return {
        "success": success_count,
        "failed": failed_count,
        "latest_status": latest.get("status", ""),
        "latest_completed_at": latest.get("completed_at", ""),
        "selected": sum(int(item.get("selected") or 0) for item in result_rows),
        "analyzed": sum(int(item.get("analyzed") or 0) for item in result_rows),
        "skipped_seen": sum(int(item.get("skipped_seen") or 0) for item in result_rows),
    }
