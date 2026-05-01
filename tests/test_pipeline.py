import json
import unittest

from biopharma_agent.analysis.pipeline import BiopharmaAnalysisPipeline
from biopharma_agent.llm.base import LLMProvider
from biopharma_agent.llm.types import (
    EmbeddingRequest,
    EmbeddingResponse,
    LLMRequest,
    LLMResponse,
    StructuredOutputRequest,
)


class FakeProvider(LLMProvider):
    provider_name = "fake"

    def chat(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(text="- ok", model="fake-model", provider="fake")

    def structured(self, request: StructuredOutputRequest) -> LLMResponse:
        return LLMResponse(
            text=json.dumps(
                {
                    "summary": "公司完成融资并推进临床项目。",
                    "language": "zh",
                    "entities": [],
                    "events": [
                        {
                            "event_type": "financing",
                            "title": "B轮融资",
                            "date": "",
                            "companies": ["测试生物"],
                            "amount": "",
                            "stage": "B",
                            "confidence": 0.9,
                            "evidence": "完成B轮融资",
                        }
                    ],
                    "relations": [],
                    "risk_signals": [],
                    "market_implications": [],
                    "needs_human_review": False,
                },
                ensure_ascii=False,
            ),
            model="fake-model",
            provider="fake",
        )

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        return EmbeddingResponse(vectors=[[0.0]], model="fake-model", provider="fake")


class PipelineTest(unittest.TestCase):
    def test_extract_insight(self):
        pipeline = BiopharmaAnalysisPipeline(FakeProvider())

        insight = pipeline.extract_insight("测试生物完成B轮融资。")

        self.assertEqual(insight["events"][0]["event_type"], "financing")

    def test_classify_event(self):
        pipeline = BiopharmaAnalysisPipeline(FakeProvider())

        self.assertEqual(pipeline.classify_event("测试生物完成B轮融资。"), "financing")


if __name__ == "__main__":
    unittest.main()

