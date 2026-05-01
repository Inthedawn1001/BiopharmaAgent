import json
import tempfile
import unittest
from pathlib import Path

from biopharma_agent.llm.base import LLMProvider
from biopharma_agent.llm.types import (
    EmbeddingRequest,
    EmbeddingResponse,
    LLMRequest,
    LLMResponse,
    StructuredOutputRequest,
)
from biopharma_agent.orchestration.workflow import LocalDocumentWorkflow
from biopharma_agent.storage.graph import LocalKnowledgeGraphWriter
from biopharma_agent.storage.local import LocalAnalysisRepository
from biopharma_agent.storage.raw_archive import LocalRawArchive


class FakeWorkflowProvider(LLMProvider):
    provider_name = "fake"

    def chat(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(text="summary", model="fake", provider="fake")

    def structured(self, request: StructuredOutputRequest) -> LLMResponse:
        return LLMResponse(
            text=json.dumps(
                {
                    "summary": "Test summary",
                    "language": "en",
                    "entities": [
                        {
                            "name": "TestBio",
                            "type": "company",
                            "normalized_name": "TestBio",
                            "confidence": 0.9,
                            "evidence": "TestBio announced completed financing",
                        }
                    ],
                    "events": [
                        {
                            "event_type": "financing",
                            "title": "Financing",
                            "date": "",
                            "companies": ["TestBio"],
                            "amount": "",
                            "stage": "",
                            "confidence": 0.9,
                            "evidence": "announced completed financing",
                        }
                    ],
                    "relations": [
                        {
                            "subject": "TestBio",
                            "predicate": "ANNOUNCED",
                            "object": "financing",
                            "confidence": 0.8,
                            "evidence": "announced completed financing",
                        }
                    ],
                    "risk_signals": [],
                    "market_implications": [],
                    "needs_human_review": False,
                },
            ),
            model="fake",
            provider="fake",
        )

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        return EmbeddingResponse(vectors=[], model="fake", provider="fake")


class WorkflowTest(unittest.TestCase):
    def test_run_text_archives_and_appends_result(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workflow = LocalDocumentWorkflow(
                llm=FakeWorkflowProvider(),
                raw_archive=LocalRawArchive(root / "raw"),
                analysis_repository=LocalAnalysisRepository(root / "processed" / "insights.jsonl"),
                graph_writer=LocalKnowledgeGraphWriter(root / "graph"),
            )

            result = workflow.run_text("TestBio announced completed financing.", document_id="doc-1")

            self.assertEqual(result.insight["summary"], "Test summary")
            self.assertTrue((root / "raw" / "manual" / "doc-1" / "raw.txt").exists())
            self.assertTrue((root / "processed" / "insights.jsonl").exists())
            self.assertTrue((root / "graph" / "nodes.jsonl").exists())
            self.assertTrue((root / "graph" / "edges.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
