import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from biopharma_agent.orchestration.scheduler import LocalRunLog, RecurringRunner


class SchedulerTest(unittest.TestCase):
    def test_run_once_records_success(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_log = LocalRunLog(Path(temp_dir) / "runs.jsonl")
            runner = RecurringRunner(run_log, clock=_fixed_clock())

            record = runner.run_once("job", lambda: {"ok": True}, metadata={"source": "test"})

            self.assertEqual(record.status, "success")
            self.assertEqual(record.result, {"ok": True})
            records = run_log.list_records()
            self.assertEqual(records[0]["job_name"], "job")
            self.assertEqual(records[0]["metadata"]["source"], "test")

    def test_run_once_records_failure_without_raising(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runner = RecurringRunner(LocalRunLog(Path(temp_dir) / "runs.jsonl"), clock=_fixed_clock())

            record = runner.run_once("job", _raise_error)

            self.assertEqual(record.status, "failed")
            self.assertIn("boom", record.error)

    def test_run_forever_respects_max_runs_and_sleep(self):
        sleeps = []
        calls = []
        runner = RecurringRunner(
            LocalRunLog(Path(tempfile.mkdtemp()) / "runs.jsonl"),
            sleep=sleeps.append,
            clock=_fixed_clock(),
        )

        records = runner.run_forever(
            "job",
            lambda: calls.append("run") or len(calls),
            interval_seconds=5,
            max_runs=3,
        )

        self.assertEqual([record.result for record in records], [1, 2, 3])
        self.assertEqual(sleeps, [5, 5])

    def test_run_log_lists_paged_records_with_summary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            run_log = LocalRunLog(Path(temp_dir) / "runs.jsonl")
            runner = RecurringRunner(run_log, clock=_fixed_clock())
            runner.run_once("job", lambda: {"ok": True})
            runner.run_once("job", _raise_error)

            page = run_log.list_records_page(limit=1, offset=0)

            self.assertEqual(page["count"], 1)
            self.assertEqual(page["total"], 2)
            self.assertTrue(page["has_more"])
            self.assertEqual(page["items"][0]["status"], "failed")
            self.assertEqual(page["summary"]["success"], 1)
            self.assertEqual(page["summary"]["failed"], 1)
            self.assertEqual(page["summary"]["selected"], 0)

    def test_run_log_summary_includes_collection_totals(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "runs.jsonl"
            rows = [
                {
                    "job_name": "fetch-sources",
                    "run_id": "run-1",
                    "status": "success",
                    "started_at": "2026-04-30T00:00:00+00:00",
                    "completed_at": "2026-04-30T00:00:01+00:00",
                    "duration_seconds": 1,
                    "result": [
                        {"source": "fda", "selected": 2, "analyzed": 1, "skipped_seen": 3},
                        {"source": "sec", "selected": 1, "analyzed": 0, "skipped_seen": 0},
                    ],
                }
            ]
            path.write_text("\n".join(__import__("json").dumps(row) for row in rows) + "\n")

            page = LocalRunLog(path).list_records_page()

            self.assertEqual(page["summary"]["selected"], 3)
            self.assertEqual(page["summary"]["analyzed"], 1)
            self.assertEqual(page["summary"]["skipped_seen"], 3)

    def test_run_log_summary_includes_daily_cycle_totals(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "runs.jsonl"
            rows = [
                {
                    "job_name": "daily-intelligence-cycle",
                    "run_id": "daily-1",
                    "status": "success",
                    "started_at": "2026-05-01T00:00:00+00:00",
                    "completed_at": "2026-05-01T00:00:01+00:00",
                    "duration_seconds": 1,
                    "result": {
                        "sources": ["fda", "sec"],
                        "fetch": [
                            {"source": "fda", "selected": 2, "analyzed": 1, "skipped_seen": 3},
                            {"source": "sec", "selected": 1, "analyzed": 0, "skipped_seen": 0},
                        ],
                        "brief": {"document_count": 8},
                    },
                }
            ]
            path.write_text("\n".join(__import__("json").dumps(row) for row in rows) + "\n")

            page = LocalRunLog(path).list_records_page()

            self.assertEqual(page["summary"]["selected"], 3)
            self.assertEqual(page["summary"]["analyzed"], 1)
            self.assertEqual(page["summary"]["skipped_seen"], 3)
            self.assertEqual(page["summary"]["briefs"], 1)
            self.assertEqual(page["summary"]["brief_document_count"], 8)
            self.assertEqual(page["summary"]["latest_brief_document_count"], 8)


def _fixed_clock():
    value = datetime(2026, 4, 30, tzinfo=timezone.utc)
    return lambda: value


def _raise_error():
    raise RuntimeError("boom")


if __name__ == "__main__":
    unittest.main()
