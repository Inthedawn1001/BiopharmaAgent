import json
import tempfile
import unittest
from pathlib import Path

from biopharma_agent.contracts import ParsedDocument, PipelineResult, RawDocument, SourceRef
from biopharma_agent.config import GraphSettings
from biopharma_agent.storage.graph import LocalKnowledgeGraphWriter
from biopharma_agent.storage.neo4j_graph import Neo4jKnowledgeGraphWriter


class GraphStorageTest(unittest.TestCase):
    def test_write_insight_creates_nodes_and_edges(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            raw = RawDocument(
                source=SourceRef(name="manual", kind="manual"),
                document_id="doc-1",
                raw_text="TestBio completed financing.",
            )
            parsed = ParsedDocument(raw=raw, text=raw.raw_text or "", checksum="abc", language="en")
            result = PipelineResult(
                document=parsed,
                model="fake",
                provider="fake",
                insight={
                    "summary": "Summary",
                    "entities": [
                        {
                            "name": "TestBio",
                            "type": "company",
                            "normalized_name": "TestBio",
                            "confidence": 0.9,
                            "evidence": "completed financing",
                        }
                    ],
                    "events": [
                        {
                            "event_type": "financing",
                            "title": "Financing",
                            "companies": ["TestBio"],
                            "evidence": "completed financing",
                        }
                    ],
                    "relations": [],
                },
            )

            writer = LocalKnowledgeGraphWriter(Path(temp_dir))
            writer.write_insight(result)

            node_lines = (Path(temp_dir) / "nodes.jsonl").read_text(encoding="utf-8").splitlines()
            edge_lines = (Path(temp_dir) / "edges.jsonl").read_text(encoding="utf-8").splitlines()
            nodes = [json.loads(line) for line in node_lines]
            edges = [json.loads(line) for line in edge_lines]

            self.assertTrue(any(node["label"] == "Company" for node in nodes))
            self.assertTrue(any(edge["predicate"] == "MENTIONS" for edge in edges))

    def test_neo4j_writer_runs_parameterized_upserts(self):
        result = _pipeline_result()
        driver = FakeNeo4jDriver()
        writer = Neo4jKnowledgeGraphWriter(
            GraphSettings(
                backend="neo4j",
                local_path="unused",
                neo4j_uri="bolt://example",
                neo4j_user="neo4j",
                neo4j_password="secret",
                neo4j_database="neo4j",
            ),
            driver=driver,
        )

        writer.write_insight(result)

        statements = [call[0] for call in driver.session_instance.tx.calls]
        self.assertTrue(any("MERGE (n:`Document`" in statement for statement in statements))
        self.assertTrue(any("MERGE (source)-[r:`MENTIONS`]" in statement for statement in statements))
        self.assertEqual(driver.session_instance.database, "neo4j")


class FakeNeo4jDriver:
    def __init__(self):
        self.session_instance = FakeNeo4jSession()

    def session(self, database=None):
        self.session_instance.database = database
        return self.session_instance


class FakeNeo4jSession:
    def __init__(self):
        self.database = None
        self.tx = FakeNeo4jTransaction()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute_write(self, callback, *args):
        return callback(self.tx, *args)


class FakeNeo4jTransaction:
    def __init__(self):
        self.calls = []

    def run(self, statement, **params):
        self.calls.append((statement, params))


def _pipeline_result():
    raw = RawDocument(
        source=SourceRef(name="manual", kind="manual"),
        document_id="doc-1",
        raw_text="TestBio completed financing.",
    )
    parsed = ParsedDocument(raw=raw, text=raw.raw_text or "", checksum="abc", language="en")
    return PipelineResult(
        document=parsed,
        model="fake",
        provider="fake",
        insight={
            "summary": "Summary",
            "entities": [
                {
                    "name": "TestBio",
                    "type": "company",
                    "normalized_name": "TestBio",
                    "confidence": 0.9,
                    "evidence": "completed financing",
                }
            ],
            "events": [],
            "relations": [],
        },
    )


if __name__ == "__main__":
    unittest.main()
