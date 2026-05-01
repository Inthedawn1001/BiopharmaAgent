import tempfile
import unittest
import json
from pathlib import Path
from unittest.mock import patch

from biopharma_agent.web import api
from biopharma_agent.web.server import STATIC_DIR


class WebApiTest(unittest.TestCase):
    def test_health(self):
        self.assertEqual(api.health()["status"], "ok")

    def test_static_index_exists(self):
        body = (STATIC_DIR / "index.html").read_text(encoding="utf-8")

        self.assertIn("Biopharma Agent Workbench", body)

    def test_deterministic_analysis(self):
        data = api.analyze_deterministic({"text": "测试生物融资增长，但存在临床失败风险"})

        self.assertIn("sentiment", data)
        self.assertIn("risk", data)

    def test_timeseries_analysis(self):
        data = api.analyze_timeseries({"values": [1, 2, 3]})

        self.assertEqual(data["trend"], "up")

    def test_feedback(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            data = api.append_feedback(
                {
                    "document_id": "doc-1",
                    "reviewer": "tester",
                    "decision": "accept",
                    "comment": "ok",
                },
                Path(temp_dir) / "feedback.jsonl",
            )

            self.assertTrue(data["ok"])

    def test_feedback_rejects_bad_decision(self):
        with self.assertRaises(ValueError):
            api.append_feedback(
                {"document_id": "doc-1", "reviewer": "tester", "decision": "maybe"},
                "unused.jsonl",
            )

    def test_list_feedback(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            path = Path(temp_dir) / "feedback.jsonl"
            api.append_feedback(
                {
                    "document_id": "doc-1",
                    "reviewer": "tester",
                    "decision": "accept",
                    "comment": "ok",
                },
                path,
            )

            data = api.list_feedback(path, limit=10)

            self.assertEqual(data["count"], 1)
            self.assertEqual(data["items"][0]["document_id"], "doc-1")

    def test_list_jsonl(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            path = Path(temp_dir) / "items.jsonl"
            path.write_text(
                json.dumps({"id": 1}) + "\n" + json.dumps({"id": 2}) + "\n",
                encoding="utf-8",
            )

            data = api.list_jsonl(path, limit=1)

            self.assertEqual(data["count"], 1)
            self.assertEqual(data["items"][0]["id"], 2)

    def test_list_jsonl_rejects_outside_workspace(self):
        with self.assertRaises(ValueError):
            api.list_jsonl("/private/tmp/outside.jsonl")

    def test_list_documents_filters_rows(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            path = Path(temp_dir) / "documents.jsonl"
            records = [
                _pipeline_record(
                    title="FDA policy update",
                    source="fda_press_releases",
                    event_type="policy",
                    risk="low",
                    summary="FDA updates policy.",
                ),
                _pipeline_record(
                    title="Biotech IPO",
                    source="biopharma_dive_news",
                    event_type="ipo",
                    risk="high",
                    summary="Company banks IPO proceeds.",
                ),
            ]
            path.write_text(
                "\n".join(json.dumps(record) for record in records) + "\n",
                encoding="utf-8",
            )

            data = api.list_documents(path, source="biopharma_dive_news", risk="high")

            self.assertEqual(data["count"], 1)
            self.assertEqual(data["items"][0]["title"], "Biotech IPO")
            self.assertEqual(data["items"][0]["event_type"], "ipo")
            self.assertIn("body_quality", data["items"][0])
            self.assertEqual(data["facets"]["sources"], ["biopharma_dive_news", "fda_press_releases"])

    def test_get_document_detail(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            path = Path(temp_dir) / "documents.jsonl"
            record = _pipeline_record(
                title="Investegate holding",
                source="investegate_announcements",
                event_type="holding",
                risk="low",
                summary="Holding update.",
            )
            record["document"]["text"] = (
                "Cleaned Investegate announcement body with details on ownership and issuer."
            )
            record["document"]["metadata"] = {
                "parser": "plain_text",
            }
            record["document"]["raw"]["metadata"] = {
                "html_cleaned": True,
                "html_extraction_method": "semantic_container",
                "original_html_length": 3000,
            }
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")

            detail = api.get_document_detail(
                "investegate-holding",
                path,
                source="investegate_announcements",
            )

            self.assertEqual(detail["document"]["id"], "investegate-holding")
            self.assertEqual(detail["quality"]["extraction_method"], "semantic_container")
            self.assertTrue(detail["quality"]["html_cleaned"])

    def test_list_runs(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            path = Path(temp_dir) / "runs.jsonl"
            rows = [
                {
                    "job_name": "fetch-sources",
                    "run_id": "run-1",
                    "status": "success",
                    "started_at": "2026-04-30T00:00:00+00:00",
                    "completed_at": "2026-04-30T00:00:01+00:00",
                    "duration_seconds": 1,
                    "result": [{"source": "fda", "selected": 1, "analyzed": 0}],
                    "metadata": {"sources": ["fda"]},
                },
                {
                    "job_name": "fetch-sources",
                    "run_id": "run-2",
                    "status": "failed",
                    "started_at": "2026-04-30T00:01:00+00:00",
                    "completed_at": "2026-04-30T00:01:01+00:00",
                    "duration_seconds": 1,
                    "error": "boom",
                    "metadata": {"sources": ["fda"]},
                },
            ]
            path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")

            data = api.list_runs(path, limit=1)

            self.assertEqual(data["count"], 1)
            self.assertEqual(data["items"][0]["run_id"], "run-2")
            self.assertEqual(data["summary"]["success"], 1)
            self.assertEqual(data["summary"]["failed"], 1)

    def test_list_sources_includes_collectors(self):
        data = api.list_sources()

        names = {item["name"]: item for item in data["items"]}
        self.assertIn("sec_biopharma_filings", names)
        self.assertEqual(names["sec_biopharma_filings"]["collector"], "sec_submissions")

    def test_diagnostics_endpoint_shape(self):
        data = api.diagnostics()

        self.assertIn("status", data)
        self.assertIn("llm", data["checks"])
        self.assertIn("storage", data["checks"])

    def test_trigger_fetch_job_records_success(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir, patch(
            "biopharma_agent.web.api.collect_sources",
            return_value=[{"source": "fda_press_releases", "selected": 1, "analyzed": 1}],
        ), patch("biopharma_agent.web.api.create_llm_provider", return_value=object()):
            run_log = Path(temp_dir) / "runs.jsonl"
            data = api.trigger_fetch_job(
                {
                    "sources": ["fda_press_releases"],
                    "limit": 1,
                    "analyze": True,
                    "run_log": str(run_log),
                    "output": str(Path(temp_dir) / "insights.jsonl"),
                    "archive_dir": str(Path(temp_dir) / "raw"),
                    "graph_dir": str(Path(temp_dir) / "graph"),
                }
            )

            self.assertTrue(data["ok"])
            self.assertTrue(run_log.exists())
            self.assertEqual(data["record"]["status"], "success")

    def test_trigger_fetch_job_records_failure(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir, patch(
            "biopharma_agent.web.api.collect_sources",
            side_effect=RuntimeError("boom"),
        ), patch("biopharma_agent.web.api.create_llm_provider", return_value=object()):
            run_log = Path(temp_dir) / "runs.jsonl"
            data = api.trigger_fetch_job(
                {
                    "sources": ["fda_press_releases"],
                    "limit": 1,
                    "analyze": True,
                    "run_log": str(run_log),
                    "output": str(Path(temp_dir) / "insights.jsonl"),
                    "archive_dir": str(Path(temp_dir) / "raw"),
                    "graph_dir": str(Path(temp_dir) / "graph"),
                }
            )

            self.assertFalse(data["ok"])
            self.assertEqual(data["record"]["status"], "failed")
            self.assertIn("boom", data["record"]["error"])


def _pipeline_record(title, source, event_type, risk, summary):
    return {
        "document": {
            "raw": {
                "document_id": title.lower().replace(" ", "-"),
                "title": title,
                "url": f"https://example.test/{title}",
                "source": {"name": source, "kind": "test"},
            },
            "checksum": title,
        },
        "provider": "test",
        "model": "test-model",
        "created_at": "2026-04-30T00:00:00+00:00",
        "insight": {
            "summary": summary,
            "events": [{"event_type": event_type, "title": event_type.upper()}],
            "risk_signals": [{"severity": risk, "risk_type": "test"}],
            "needs_human_review": False,
        },
    }


if __name__ == "__main__":
    unittest.main()
