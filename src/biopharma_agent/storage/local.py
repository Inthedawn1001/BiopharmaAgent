"""Local filesystem analysis storage for development and smoke tests."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any

from biopharma_agent.contracts import PipelineResult
from biopharma_agent.storage.raw_archive import LocalRawArchive
from biopharma_agent.storage.repository import (
    DocumentFilters,
    DocumentListResult,
    find_document_detail,
    pipeline_record_key,
    query_documents_from_records,
)


class LocalAnalysisRepository:
    """Append pipeline results to JSONL for easy inspection and replay."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def append(self, result: PipelineResult) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(_to_jsonable(asdict(result)), ensure_ascii=False) + "\n")
        return self.path

    def list_records(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if offset < 0:
            raise ValueError("offset must be non-negative")
        records = self._read_records()
        return records[offset : offset + limit]

    def list_documents(self, filters: DocumentFilters) -> DocumentListResult:
        records = self._read_records()
        return query_documents_from_records(records, filters, path=str(self.path))

    def get_document(self, document_id: str, source: str = "") -> dict[str, Any] | None:
        return find_document_detail(self._read_records(), document_id, source=source)

    def _read_records(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        records: list[dict[str, Any]] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            decoded = json.loads(line)
            if isinstance(decoded, dict):
                records.append(decoded)
        return records


class IdempotentLocalAnalysisRepository(LocalAnalysisRepository):
    """JSONL repository that replaces an existing result with the same pipeline key."""

    def append(self, result: PipelineResult) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = _to_jsonable(asdict(result))
        key = pipeline_record_key(payload)
        records = [
            record for record in self._read_records() if pipeline_record_key(record) != key
        ]
        records.append(payload)
        temp_path = self.path.with_suffix(self.path.suffix + ".tmp")
        with temp_path.open("w", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        temp_path.replace(self.path)
        return self.path


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    return value
