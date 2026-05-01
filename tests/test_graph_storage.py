import json
import tempfile
import unittest
from pathlib import Path

from biopharma_agent.contracts import ParsedDocument, PipelineResult, RawDocument, SourceRef
from biopharma_agent.storage.graph import LocalKnowledgeGraphWriter


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


if __name__ == "__main__":
    unittest.main()
