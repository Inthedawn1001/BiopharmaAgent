import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from biopharma_agent.config import GraphSettings, StorageSettings
from biopharma_agent.contracts import ParsedDocument, PipelineResult, RawDocument, SourceRef
from biopharma_agent.ops.factory import create_feedback_repository
from biopharma_agent.ops.feedback import FeedbackRecord, LocalFeedbackRepository
from biopharma_agent.orchestration.source_state import LocalSourceStateStore
from biopharma_agent.orchestration.postgres_source_state import PostgresSourceStateStore
from biopharma_agent.storage.postgres import PostgresAnalysisRepository
from biopharma_agent.storage.factory import (
    create_analysis_repository,
    create_graph_writer,
    create_source_state_store,
)
from biopharma_agent.storage.graph import LocalKnowledgeGraphWriter
from biopharma_agent.storage.local import IdempotentLocalAnalysisRepository, LocalAnalysisRepository
from biopharma_agent.storage.repository import DocumentFilters


class StorageRepositoryTest(unittest.TestCase):
    def test_local_repository_lists_filtered_documents_with_pagination(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = LocalAnalysisRepository(Path(temp_dir) / "insights.jsonl")
            repository.append(_result("doc-1", "fda", "policy", "low", "2026-04-29T00:00:00+00:00"))
            repository.append(_result("doc-2", "news", "ipo", "high", "2026-04-30T00:00:00+00:00"))

            data = repository.list_documents(
                DocumentFilters(
                    limit=1,
                    source="news",
                    risk="high",
                    sort_direction="desc",
                )
            )

            self.assertEqual(data.count, 1)
            self.assertEqual(data.filtered_total, 1)
            self.assertEqual(data.total, 2)
            self.assertEqual(data.items[0]["id"], "doc-2")
            self.assertEqual(data.facets["sources"], ["fda", "news"])
            self.assertEqual(data.items[0]["body_quality"], "weak")
            self.assertEqual(data.items[0]["text_length"], len("news ipo"))

    def test_local_repository_gets_document_detail_with_quality(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = LocalAnalysisRepository(Path(temp_dir) / "insights.jsonl")
            repository.append(
                _result(
                    "doc-1",
                    "investegate",
                    "holding",
                    "low",
                    "2026-04-30T00:00:00+00:00",
                    text=(
                        "Holding update body with enough detail about share ownership, "
                        "company identifiers, market context, and disclosure rationale "
                        "to pass the short quality threshold."
                    ),
                    metadata={
                        "parser": "plain_text",
                    },
                    raw_metadata={
                        "html_cleaned": True,
                        "html_extraction_method": "semantic_container",
                        "original_html_length": 4000,
                    },
                )
            )

            detail = repository.get_document("doc-1", source="investegate")

            self.assertIsNotNone(detail)
            self.assertEqual(detail["document"]["id"], "doc-1")
            self.assertEqual(detail["quality"]["label"], "short")
            self.assertTrue(detail["quality"]["html_cleaned"])
            self.assertEqual(detail["quality"]["extraction_method"], "semantic_container")
            self.assertIn("Holding update body", detail["document"]["text_preview"])

    def test_idempotent_repository_replaces_existing_pipeline_key(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "insights.jsonl"
            repository = IdempotentLocalAnalysisRepository(path)

            repository.append(_result("doc-1", "fda", "policy", "low", "2026-04-29T00:00:00+00:00"))
            repository.append(_result("doc-1", "fda", "policy", "high", "2026-04-30T00:00:00+00:00"))

            lines = path.read_text(encoding="utf-8").splitlines()
            records = [json.loads(line) for line in lines]
            risk = records[0]["insight"]["risk_signals"][0]["severity"]
            self.assertEqual(len(records), 1)
            self.assertEqual(risk, "high")

    def test_factory_selects_jsonl_repository(self):
        settings = StorageSettings(
            backend="jsonl",
            analysis_jsonl_path="unused.jsonl",
            feedback_jsonl_path="feedback.jsonl",
            source_state_path="source_state.json",
            postgres_dsn="",
        )

        repository = create_analysis_repository(settings, path="custom.jsonl", idempotent=True)

        self.assertIsInstance(repository, IdempotentLocalAnalysisRepository)

    def test_feedback_repository_lists_records(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "feedback.jsonl"
            repository = LocalFeedbackRepository(path)
            repository.append(
                FeedbackRecord(
                    document_id="doc-1",
                    reviewer="tester",
                    decision="accept",
                    comment="ok",
                )
            )

            payload = repository.list_records(limit=10)

            self.assertEqual(payload["count"], 1)
            self.assertEqual(payload["items"][0]["document_id"], "doc-1")

    def test_factory_selects_feedback_jsonl_repository(self):
        settings = StorageSettings(
            backend="jsonl",
            analysis_jsonl_path="unused.jsonl",
            feedback_jsonl_path="feedback.jsonl",
            source_state_path="source_state.json",
            postgres_dsn="",
        )

        repository = create_feedback_repository(settings, path="custom-feedback.jsonl")

        self.assertIsInstance(repository, LocalFeedbackRepository)

    def test_factory_selects_source_state_jsonl_repository(self):
        settings = StorageSettings(
            backend="jsonl",
            analysis_jsonl_path="unused.jsonl",
            feedback_jsonl_path="feedback.jsonl",
            source_state_path="source_state.json",
            postgres_dsn="",
        )

        store = create_source_state_store(settings)

        self.assertIsInstance(store, LocalSourceStateStore)

    def test_factory_selects_source_state_postgres_repository(self):
        settings = StorageSettings(
            backend="postgres",
            analysis_jsonl_path="unused.jsonl",
            feedback_jsonl_path="feedback.jsonl",
            source_state_path="source_state.json",
            postgres_dsn="postgresql://example",
        )

        store = create_source_state_store(settings)

        self.assertIsInstance(store, PostgresSourceStateStore)

    def test_factory_selects_graph_jsonl_writer(self):
        settings = GraphSettings(
            backend="jsonl",
            local_path="data/graph",
            neo4j_uri="",
            neo4j_user="",
            neo4j_password="",
            neo4j_database="neo4j",
        )

        writer = create_graph_writer(settings, path="custom-graph")

        self.assertIsInstance(writer, LocalKnowledgeGraphWriter)

    def test_factory_can_disable_graph_writer(self):
        settings = GraphSettings(
            backend="none",
            local_path="data/graph",
            neo4j_uri="",
            neo4j_user="",
            neo4j_password="",
            neo4j_database="neo4j",
        )

        self.assertIsNone(create_graph_writer(settings))

    def test_postgres_list_documents_uses_sql_filters_and_pagination(self):
        repository = FakePostgresAnalysisRepository()

        payload = repository.list_documents(
            DocumentFilters(
                limit=1,
                offset=1,
                source="fda",
                event_type="policy",
                risk="high",
                query="formula",
                sort_by="source",
                sort_direction="desc",
            )
        )

        self.assertEqual(payload.count, 1)
        self.assertEqual(payload.total, 3)
        self.assertEqual(payload.filtered_total, 3)
        self.assertTrue(payload.has_more)
        self.assertEqual(payload.items[0]["source"], "fda")
        executed_sql = "\n".join(sql for sql, _ in repository.cursor.calls)
        self.assertIn("where s.name = %s", executed_sql)
        self.assertIn("i.event_type = %s", executed_sql)
        self.assertIn("i.risk = %s", executed_sql)
        self.assertIn("order by s.name desc", executed_sql)


def _result(
    document_id,
    source,
    event_type,
    risk,
    created_at,
    text=None,
    metadata=None,
    raw_metadata=None,
):
    raw_text = text or f"{source} {event_type}"
    raw = RawDocument(
        source=SourceRef(name=source, kind="test"),
        document_id=document_id,
        title=f"{source} {event_type}",
        raw_text=raw_text,
        metadata=raw_metadata or {},
    )
    parsed = ParsedDocument(
        raw=raw,
        text=raw.raw_text or "",
        checksum=document_id,
        language="en",
        metadata=metadata or {},
    )
    result = PipelineResult(
        document=parsed,
        model="model",
        provider="provider",
        created_at=created_at,
        insight={
            "summary": f"{source} summary",
            "events": [{"event_type": event_type, "title": event_type.upper()}],
            "risk_signals": [{"severity": risk, "risk_type": "test"}],
            "needs_human_review": risk == "high",
        },
    )
    return result


class FakePostgresAnalysisRepository(PostgresAnalysisRepository):
    def __init__(self):
        self.cursor = FakeCursor()
        self.connection = FakeConnection(self.cursor)

    def _connect(self):
        return self.connection


class FakeConnection:
    def __init__(self, cursor):
        self.cursor_instance = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return self.cursor_instance


class FakeCursor:
    def __init__(self):
        self.calls = []
        self.result = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split())
        self.calls.append((normalized, list(params or [])))
        if normalized == "select count(*) from insights":
            self.result = [(3,)]
        elif normalized.startswith("select count(*) from insights i"):
            self.result = [(3,)]
        elif normalized.startswith("select i.pipeline_payload"):
            self.result = [(_pipeline_payload(), "doc-1", "FDA formula", "https://example.test", "fda", "regulatory_feed", datetime(2026, 4, 30, tzinfo=timezone.utc), "deepseek", "deepseek-chat", "summary", "policy", "high", True)]
        elif normalized.startswith("select name from sources"):
            self.result = [("fda",), ("news",)]
        elif normalized.startswith("select distinct event_type"):
            self.result = [("policy",)]
        elif normalized.startswith("select distinct risk"):
            self.result = [("high",), ("low",)]
        else:
            self.result = []

    def fetchone(self):
        return self.result[0]

    def fetchall(self):
        return self.result


def _pipeline_payload():
    return {
        "document": {
            "raw": {
                "document_id": "doc-1",
                "title": "FDA formula",
                "url": "https://example.test",
                "source": {"name": "fda", "kind": "regulatory_feed"},
            },
            "checksum": "doc-1",
        },
        "provider": "deepseek",
        "model": "deepseek-chat",
        "created_at": "2026-04-30T00:00:00+00:00",
        "insight": {
            "summary": "summary",
            "events": [{"event_type": "policy", "title": "Policy update"}],
            "risk_signals": [{"severity": "high"}],
            "needs_human_review": True,
        },
    }


if __name__ == "__main__":
    unittest.main()
