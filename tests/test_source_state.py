import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from biopharma_agent.contracts import RawDocument, SourceRef
from biopharma_agent.orchestration.source_state import (
    LocalSourceStateStore,
    classify_source_error,
    state_summary,
)


class SourceStateTest(unittest.TestCase):
    def test_records_success_and_seen_documents(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "source_state.json"
            source = SourceRef(
                name="fda_press_releases",
                kind="regulatory_feed",
                metadata={"collector": "feed", "category": "regulatory"},
            )
            store = LocalSourceStateStore(path)

            record = store.record_success(
                source,
                started_at=_fixed_time(),
                completed_at=_fixed_time(),
                summary={"fetched": 2, "selected": 1, "analyzed": 1, "skipped_seen": 1},
                documents=[
                    RawDocument(source=source, document_id="doc-1", title="One"),
                    RawDocument(source=source, document_id="doc-1", title="One duplicate"),
                ],
            )

            self.assertEqual(record["last_status"], "success")
            self.assertEqual(record["failure_type"], "none")
            self.assertEqual(record["failure_severity"], "info")
            self.assertEqual(record["seen_document_ids"], ["doc-1"])
            self.assertEqual(store.seen_document_ids("fda_press_releases"), {"doc-1"})
            self.assertEqual(record["last_skipped_seen"], 1)

    def test_records_failure_without_dropping_seen_documents(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "source_state.json"
            source = SourceRef(name="sec_biopharma_filings", kind="market_regulatory_api")
            store = LocalSourceStateStore(path)
            store.record_success(
                source,
                started_at=_fixed_time(),
                completed_at=_fixed_time(),
                summary={"selected": 1},
                documents=[RawDocument(source=source, document_id="sec-doc")],
            )

            record = store.record_failure(
                source,
                started_at=_fixed_time(),
                completed_at=_fixed_time(),
                error="rate limited",
            )

            self.assertEqual(record["last_status"], "failed")
            self.assertEqual(record["last_error"], "rate limited")
            self.assertEqual(record["failure_type"], "rate_limit")
            self.assertEqual(record["failure_severity"], "warning")
            self.assertIn("request rate", record["remediation_hint"])
            self.assertEqual(record["seen_document_ids"], ["sec-doc"])
            self.assertEqual(record["consecutive_failures"], 1)

    def test_state_summary_includes_never_run_sources(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "source_state.json"
            source = SourceRef(name="asx_biopharma_announcements", kind="market_announcement_api")

            data = state_summary(path, sources=[source])

            self.assertEqual(data["count"], 1)
            self.assertEqual(data["items"][0]["last_status"], "never_run")
            self.assertEqual(data["items"][0]["failure_type"], "none")
            self.assertEqual(data["summary"]["never_run"], 1)
            self.assertEqual(data["backend"], "jsonl")
            self.assertEqual(data["summary"]["health_ratio"], 0.0)
            self.assertEqual(data["summary"]["failure_types"], {})

    def test_classifies_common_failure_modes(self):
        cases = [
            ("HTTP 403 forbidden", "auth", "error"),
            ("HTTP 429 too many requests", "rate_limit", "warning"),
            ("Connection timeout while opening RSS", "network", "warning"),
            ("JSONDecodeError while parsing submissions", "parser", "warning"),
            ("DeepSeek LLM provider missing API key", "llm", "error"),
            ("Postgres permission denied", "storage", "error"),
        ]

        for error, expected_type, expected_severity in cases:
            with self.subTest(error=error):
                diagnosis = classify_source_error(error, status="failed")

                self.assertEqual(diagnosis["failure_type"], expected_type)
                self.assertEqual(diagnosis["failure_severity"], expected_severity)
                self.assertTrue(diagnosis["remediation_hint"])

    def test_classifies_disabled_source(self):
        diagnosis = classify_source_error("", status="never_run", enabled=False)

        self.assertEqual(diagnosis["failure_type"], "disabled")
        self.assertEqual(diagnosis["failure_severity"], "info")


def _fixed_time():
    return datetime(2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc)


if __name__ == "__main__":
    unittest.main()
