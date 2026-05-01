"""Knowledge graph writer contracts and local JSONL implementation."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from biopharma_agent.contracts import PipelineResult


class KnowledgeGraphWriter(Protocol):
    def write_insight(self, result: PipelineResult) -> None:
        """Write entities and relations extracted from one pipeline result."""


@dataclass(frozen=True)
class GraphNode:
    node_id: str
    label: str
    properties: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphEdge:
    source_id: str
    target_id: str
    predicate: str
    properties: dict[str, Any] = field(default_factory=dict)


class LocalKnowledgeGraphWriter:
    """Append graph-shaped records to JSONL files for later Neo4j import."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)
        self.nodes_path = self.root / "nodes.jsonl"
        self.edges_path = self.root / "edges.jsonl"

    def write_insight(self, result: PipelineResult) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        nodes = nodes_from_result(result)
        edges = edges_from_result(result)
        self._append_jsonl(self.nodes_path, [node.__dict__ for node in nodes])
        self._append_jsonl(self.edges_path, [edge.__dict__ for edge in edges])

    def _append_jsonl(self, path: Path, rows: list[dict[str, Any]]) -> None:
        with path.open("a", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def nodes_from_result(result: PipelineResult) -> list[GraphNode]:
    insight = result.insight
    nodes: dict[str, GraphNode] = {}

    document_node = GraphNode(
        node_id=f"document:{result.document.checksum}",
        label="Document",
        properties={
            "title": result.document.raw.title,
            "url": result.document.raw.url,
            "source": result.document.raw.source.name,
            "summary": insight.get("summary", ""),
            "language": result.document.language,
        },
    )
    nodes[document_node.node_id] = document_node

    for entity in insight.get("entities", []):
        name = entity.get("normalized_name") or entity.get("name")
        if not name:
            continue
        node_id = _node_id(str(entity.get("type", "entity")), str(name))
        nodes[node_id] = GraphNode(
            node_id=node_id,
            label=str(entity.get("type", "Entity")).title(),
            properties={
                "name": entity.get("name", name),
                "normalized_name": name,
                "confidence": entity.get("confidence"),
                "evidence": entity.get("evidence"),
            },
        )

    for event in insight.get("events", []):
        title = event.get("title")
        if not title:
            continue
        node_id = _node_id("event", f"{event.get('event_type', 'other')}:{title}")
        nodes[node_id] = GraphNode(
            node_id=node_id,
            label="Event",
            properties={
                "event_type": event.get("event_type"),
                "title": title,
                "date": event.get("date"),
                "amount": event.get("amount"),
                "stage": event.get("stage"),
                "confidence": event.get("confidence"),
                "evidence": event.get("evidence"),
            },
        )

    return list(nodes.values())


def edges_from_result(result: PipelineResult) -> list[GraphEdge]:
    insight = result.insight
    document_id = f"document:{result.document.checksum}"
    edges: list[GraphEdge] = []

    for entity in insight.get("entities", []):
        name = entity.get("normalized_name") or entity.get("name")
        if name:
            edges.append(
                GraphEdge(
                    source_id=document_id,
                    target_id=_node_id(str(entity.get("type", "entity")), str(name)),
                    predicate="MENTIONS",
                    properties={"evidence": entity.get("evidence")},
                )
            )

    for event in insight.get("events", []):
        title = event.get("title")
        if title:
            event_id = _node_id("event", f"{event.get('event_type', 'other')}:{title}")
            edges.append(
                GraphEdge(
                    source_id=document_id,
                    target_id=event_id,
                    predicate="REPORTS",
                    properties={"evidence": event.get("evidence")},
                )
            )
            for company in event.get("companies", []):
                edges.append(
                    GraphEdge(
                        source_id=_node_id("company", str(company)),
                        target_id=event_id,
                        predicate="PARTICIPATES_IN",
                        properties={"event_type": event.get("event_type")},
                    )
                )

    for relation in insight.get("relations", []):
        subject = relation.get("subject")
        obj = relation.get("object")
        predicate = relation.get("predicate")
        if subject and obj and predicate:
            edges.append(
                GraphEdge(
                    source_id=_node_id("entity", str(subject)),
                    target_id=_node_id("entity", str(obj)),
                    predicate=str(predicate),
                    properties={
                        "confidence": relation.get("confidence"),
                        "evidence": relation.get("evidence"),
                        "document_id": document_id,
                    },
                )
            )

    return edges


def _node_id(label: str, value: str) -> str:
    normalized = " ".join(value.lower().strip().split())
    return f"{label.lower()}:{normalized}"
