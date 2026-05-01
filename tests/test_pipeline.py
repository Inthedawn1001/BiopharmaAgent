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
                    "summary": "The company completed financing and advanced its clinical program.",
                    "language": "en",
                    "entities": [],
                    "events": [
                        {
                            "event_type": "financing",
                            "title": "Series B financing",
                            "date": "",
                            "companies": ["TestBio"],
                            "amount": "",
                            "stage": "B",
                            "confidence": 0.9,
                            "evidence": "completed Series B financing",
                        }
                    ],
                    "relations": [],
                    "risk_signals": [],
                    "market_implications": [],
                    "needs_human_review": False,
                },
            ),
            model="fake-model",
            provider="fake",
        )

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        return EmbeddingResponse(vectors=[[0.0]], model="fake-model", provider="fake")


class PipelineTest(unittest.TestCase):
    def test_extract_insight(self):
        pipeline = BiopharmaAnalysisPipeline(FakeProvider())

        insight = pipeline.extract_insight("TestBio completed Series B financing.")

        self.assertEqual(insight["events"][0]["event_type"], "financing")

    def test_classify_event(self):
        pipeline = BiopharmaAnalysisPipeline(FakeProvider())

        self.assertEqual(pipeline.classify_event("TestBio completed Series B financing."), "financing")


if __name__ == "__main__":
    unittest.main()
