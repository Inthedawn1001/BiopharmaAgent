import unittest
from datetime import datetime, timezone
from pathlib import Path

from biopharma_agent.ops.source_report import build_source_health_report


class SourceReportTest(unittest.TestCase):
    def test_builds_markdown_report_from_source_state_and_runs(self):
        report = build_source_health_report(
            {
                "path": "data/runs/source_state.json",
                "backend": "jsonl",
                "count": 2,
                "summary": {
                    "success": 1,
                    "failed": 1,
                    "never_run": 0,
                    "health_ratio": 0.5,
                    "alert_counts": {"critical": 1, "warning": 0, "info": 0, "total": 1},
                },
                "alerts": [
                    {
                        "level": "critical",
                        "source": "sec_biopharma_filings",
                        "category": "storage",
                        "action": "Check Postgres.",
                        "consecutive_failures": 1,
                    }
                ],
                "items": [
                    {
                        "source": "fda_press_releases",
                        "last_status": "success",
                        "failure_type": "none",
                        "seen_count": 3,
                        "last_completed_at": "2026-05-01T00:00:00+00:00",
                    },
                    {
                        "source": "sec_biopharma_filings",
                        "last_status": "failed",
                        "failure_type": "storage",
                        "seen_count": 1,
                        "last_completed_at": "2026-05-01T00:01:00+00:00",
                    },
                ],
            },
            {
                "path": "data/runs/fetch_runs.jsonl",
                "summary": {
                    "success": 2,
                    "failed": 1,
                    "latest_status": "failed",
                    "latest_completed_at": "2026-05-01T00:02:00+00:00",
                    "selected": 4,
                    "analyzed": 2,
                    "skipped_seen": 1,
                },
                "items": [
                    {
                        "job_name": "fetch-sources",
                        "run_id": "run-1",
                        "status": "failed",
                        "completed_at": "2026-05-01T00:02:00+00:00",
                        "error": "boom",
                        "metadata": {"sources": ["sec_biopharma_filings"]},
                    }
                ],
            },
            generated_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        )

        self.assertEqual(report["summary"]["source_count"], 2)
        self.assertEqual(report["summary"]["alert_counts"]["critical"], 1)
        self.assertIn("# Biopharma Agent Source Health Report", report["markdown"])
        self.assertIn("sec_biopharma_filings", report["markdown"])
        self.assertIn("Check Postgres.", report["markdown"])
        self.assertIn("run-1", report["markdown"])

    def test_report_redacts_absolute_paths_outside_workspace(self):
        report = build_source_health_report(
            {
                "path": "/private/tmp/source_state.json",
                "backend": "jsonl",
                "count": 0,
                "summary": {},
                "alerts": [],
                "items": [],
            },
            {
                "path": str(Path.cwd() / "data/runs/fetch_runs.jsonl"),
                "summary": {},
                "items": [],
            },
            generated_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
        )

        self.assertIn("Source state path: <external>/source_state.json", report["markdown"])
        self.assertIn("Run log path: data/runs/fetch_runs.jsonl", report["markdown"])


if __name__ == "__main__":
    unittest.main()
