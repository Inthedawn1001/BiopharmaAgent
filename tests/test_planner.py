import json
import unittest

from biopharma_agent.agent.planner import LLMTaskPlanner
from biopharma_agent.llm.base import LLMProvider
from biopharma_agent.llm.types import (
    EmbeddingRequest,
    EmbeddingResponse,
    LLMRequest,
    LLMResponse,
    StructuredOutputRequest,
)


class FakePlannerProvider(LLMProvider):
    provider_name = "fake"

    def chat(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(text="ok", model="fake", provider="fake")

    def structured(self, request: StructuredOutputRequest) -> LLMResponse:
        return LLMResponse(
            text=json.dumps(
                {
                    "document_type": "news",
                    "priority": "high",
                    "recommended_steps": ["summarize", "extract_events", "human_review"],
                    "reason": "Financing events require fast tracking.",
                },
            ),
            model="fake",
            provider="fake",
        )

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        return EmbeddingResponse(vectors=[], model="fake", provider="fake")


class PlannerTest(unittest.TestCase):
    def test_planner_returns_routing_plan(self):
        planner = LLMTaskPlanner(FakePlannerProvider())

        plan = planner.plan("A company completed financing.")

        self.assertEqual(plan["document_type"], "news")
        self.assertIn("extract_events", plan["recommended_steps"])


if __name__ == "__main__":
    unittest.main()
