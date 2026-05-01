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
    LLMUsage,
    StructuredOutputRequest,
)
from biopharma_agent.ops.feedback import FeedbackRecord, LocalFeedbackRepository
from biopharma_agent.ops.llm_observer import ObservedLLMProvider
from biopharma_agent.ops.metrics import InMemoryMetrics


class FakeObservedProvider(LLMProvider):
    provider_name = "fake"

    def chat(self, request: LLMRequest) -> LLMResponse:
        return LLMResponse(
            text="ok",
            model="fake",
            provider="fake",
            usage=LLMUsage(total_tokens=3),
        )

    def structured(self, request: StructuredOutputRequest) -> LLMResponse:
        return self.chat(LLMRequest(messages=request.messages))

    def embed(self, request: EmbeddingRequest) -> EmbeddingResponse:
        return EmbeddingResponse(vectors=[[0.0]], model="fake", provider="fake")


class OpsTest(unittest.TestCase):
    def test_observed_provider_records_metrics(self):
        metrics = InMemoryMetrics()
        provider = ObservedLLMProvider(FakeObservedProvider(), metrics)

        provider.chat(LLMRequest(messages=[]))

        snapshot = metrics.snapshot()
        self.assertEqual(snapshot["counters"]["llm.requests{operation=chat,provider=fake}"], 1.0)
        self.assertEqual(snapshot["counters"]["llm.tokens{operation=chat,provider=fake}"], 3.0)

    def test_feedback_repository(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "feedback.jsonl"

            LocalFeedbackRepository(path).append(
                FeedbackRecord(document_id="doc-1", reviewer="user", decision="accept")
            )

            record = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(record["document_id"], "doc-1")


if __name__ == "__main__":
    unittest.main()

