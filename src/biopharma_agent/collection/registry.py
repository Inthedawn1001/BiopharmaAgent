"""Source registry for crawler and fetcher modules."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from biopharma_agent.contracts import SourceRef


class SourceRegistry:
    """In-memory registry with JSON load/save helpers."""

    def __init__(self) -> None:
        self._sources: dict[str, SourceRef] = {}

    def register(self, source: SourceRef) -> None:
        self._sources[source.name] = source

    def get(self, name: str) -> SourceRef:
        return self._sources[name]

    def list(self) -> list[SourceRef]:
        return list(self._sources.values())

    @classmethod
    def from_json(cls, path: Path | str) -> "SourceRegistry":
        registry = cls()
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        for item in payload:
            registry.register(
                SourceRef(
                    name=item["name"],
                    kind=item["kind"],
                    url=item.get("url"),
                    metadata=item.get("metadata", {}),
                )
            )
        return registry

    def to_json(self, path: Path | str) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps([asdict(source) for source in self.list()], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return output

