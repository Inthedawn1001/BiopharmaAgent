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
                    "summary": "测试摘要",
                    "language": "zh",
                    "entities": [
                        {
                            "name": "测试生物",
                            "type": "company",
                            "normalized_name": "测试生物",
                            "confidence": 0.9,
                            "evidence": "测试生物宣布完成融资",
                        }
                    ],
                    "events": [
                        {
                            "event_type": "financing",
                            "title": "融资",
                            "date": "",
                            "companies": ["测试生物"],
                            "amount": "",
                            "stage": "",
                            "confidence": 0.9,
                            "evidence": "宣布完成融资",
                        }
                    ],
                    "relations": [
                        {
                            "subject": "测试生物",
                            "predicate": "ANNOUNCED",
                            "object": "融资",
                            "confidence": 0.8,
                            "evidence": "宣布完成融资",
                        }
                    ],
                    "risk_signals": [],
                    "market_implications": [],
                    "needs_human_review": False,
                },
                ensure_ascii=False,
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

            result = workflow.run_text("测试生物宣布完成融资。", document_id="doc-1")

            self.assertEqual(result.insight["summary"], "测试摘要")
            self.assertTrue((root / "raw" / "manual" / "doc-1" / "raw.txt").exists())
            self.assertTrue((root / "processed" / "insights.jsonl").exists())
            self.assertTrue((root / "graph" / "nodes.jsonl").exists())
            self.assertTrue((root / "graph" / "edges.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
