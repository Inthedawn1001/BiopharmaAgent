import os
import unittest

from biopharma_agent.ops.feedback import FeedbackRecord
from biopharma_agent.ops.postgres_feedback import PostgresFeedbackRepository
from biopharma_agent.storage.postgres import PostgresAnalysisRepository
from biopharma_agent.storage.repository import DocumentFilters

from tests.test_storage_repository import _result


@unittest.skipUnless(
    os.getenv("BIOPHARMA_RUN_POSTGRES_TESTS") == "1",
    "Set BIOPHARMA_RUN_POSTGRES_TESTS=1 and BIOPHARMA_POSTGRES_DSN to run.",
)
class PostgresIntegrationTest(unittest.TestCase):
    def test_postgres_repositories_roundtrip(self):
        dsn = os.environ["BIOPHARMA_POSTGRES_DSN"]
        analysis_repository = PostgresAnalysisRepository(dsn)
        feedback_repository = PostgresFeedbackRepository(dsn)

        result = _result(
            document_id="integration-doc",
            source="integration_source",
            event_type="financing",
            risk="medium",
            created_at="2026-04-30T00:00:00+00:00",
        )
        analysis_repository.append(result)
        feedback_repository.append(
            FeedbackRecord(
                document_id="integration-doc",
                reviewer="integration-test",
                decision="accept",
                comment="ok",
            )
        )

        documents = analysis_repository.list_documents(
            DocumentFilters(source="integration_source", event_type="financing", risk="medium")
        )
        feedback = feedback_repository.list_records(limit=20)

        self.assertGreaterEqual(documents.filtered_total, 1)
        self.assertTrue(any(item["id"] == "integration-doc" for item in documents.items))
        self.assertTrue(
            any(item["document_id"] == "integration-doc" for item in feedback["items"])
        )


if __name__ == "__main__":
    unittest.main()
