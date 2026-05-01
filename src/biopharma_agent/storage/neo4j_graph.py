"""Neo4j knowledge graph writer."""

from __future__ import annotations

import importlib
import re
from typing import Any

from biopharma_agent.config import GraphSettings
from biopharma_agent.contracts import PipelineResult
from biopharma_agent.storage.graph import GraphEdge, GraphNode, edges_from_result, nodes_from_result


class Neo4jKnowledgeGraphWriter:
    """Write extracted document knowledge graphs to Neo4j."""

    def __init__(
        self,
        settings: GraphSettings,
        *,
        driver: Any | None = None,
    ) -> None:
        if not settings.neo4j_uri:
            raise ValueError("Neo4j URI is required")
        self.settings = settings
        self._driver = driver or self._create_driver(settings)

    def write_insight(self, result: PipelineResult) -> None:
        nodes = nodes_from_result(result)
        edges = edges_from_result(result)
        with self._driver.session(database=self.settings.neo4j_database or None) as session:
            session.execute_write(_write_graph, nodes, edges)

    def close(self) -> None:
        close = getattr(self._driver, "close", None)
        if close:
            close()

    def _create_driver(self, settings: GraphSettings) -> Any:
        neo4j = importlib.import_module("neo4j")
        auth = (settings.neo4j_user, settings.neo4j_password) if settings.neo4j_user else None
        return neo4j.GraphDatabase.driver(settings.neo4j_uri, auth=auth)


def _write_graph(tx: Any, nodes: list[GraphNode], edges: list[GraphEdge]) -> None:
    for node in nodes:
        label = _safe_label(node.label)
        tx.run(
            f"MERGE (n:`{label}` {{id: $id}}) SET n += $properties",
            id=node.node_id,
            properties=_clean_properties(node.properties),
        )
    for edge in edges:
        predicate = _safe_label(edge.predicate)
        tx.run(
            f"""
            MATCH (source {{id: $source_id}})
            MATCH (target {{id: $target_id}})
            MERGE (source)-[r:`{predicate}`]->(target)
            SET r += $properties
            """,
            source_id=edge.source_id,
            target_id=edge.target_id,
            properties=_clean_properties(edge.properties),
        )


def _safe_label(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", str(value or "Entity")).strip("_")
    return cleaned or "Entity"


def _clean_properties(values: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in values.items():
        if value is None:
            continue
        cleaned[str(key)] = value
    return cleaned
