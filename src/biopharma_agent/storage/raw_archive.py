"""Raw document archive contracts and implementations."""

from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from biopharma_agent.contracts import RawDocument


class RawArchive(Protocol):
    """Storage boundary for raw collected documents."""

    def save(self, raw: RawDocument) -> str:
        """Persist a raw document and return a durable URI."""


class LocalRawArchive:
    """Persist raw documents as UTF-8 text plus metadata JSON."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def save(self, raw: RawDocument) -> str:
        document_dir = self.root / raw.source.name / raw.document_id
        document_dir.mkdir(parents=True, exist_ok=True)
        text_path = document_dir / "raw.txt"
        metadata_path = document_dir / "metadata.json"

        text_path.write_text(raw.raw_text or "", encoding="utf-8")
        metadata_path.write_text(
            json.dumps(to_jsonable(asdict(raw)), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return str(text_path)


def to_jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_jsonable(item) for item in value]
    return value
