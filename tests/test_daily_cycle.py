import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from biopharma_agent.orchestration.daily_cycle import DailyCycleOptions, run_daily_intelligence_cycle


class DailyCycleTest(unittest.TestCase):
    def test_daily_cycle_runs_fetch_and_writes_brief_artifacts(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            output = root / "insights.jsonl"
            output.write_text(json.dumps(_pipeline_record()) + "\n", encoding="utf-8")

            with patch(
                "biopharma_agent.orchestration.daily_cycle.collect_sources",
                return_value=[{"source": "fda_medwatch", "selected": 1, "analyzed": 1}],
            ) as collect:
                result = run_daily_intelligence_cycle(
                    DailyCycleOptions(
                        profile="global_safety_alerts",
                        limit=1,
                        analyze=False,
                        archive_dir=root / "raw",
                        output=output,
                        graph_dir=root / "graph",
                        state_path=root / "source_state.json",
                        run_log=root / "daily.jsonl",
                        report_md=root / "brief.md",
                        report_json=root / "brief.json",
                    )
                )

            self.assertTrue(result["ok"])
            self.assertTrue((root / "daily.jsonl").exists())
            self.assertTrue((root / "brief.md").exists())
            self.assertTrue((root / "brief.json").exists())
            record = result["record"]
            self.assertEqual(record["status"], "success")
            self.assertEqual(record["metadata"]["profile"], "global_safety_alerts")
            self.assertEqual(record["metadata"]["source_names"], ["fda_medwatch", "mhra_drug_device_alerts"])
            self.assertEqual(record["result"]["brief"]["document_count"], 1)
            collect.assert_called_once()

    def test_daily_cycle_records_failure(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            with patch(
                "biopharma_agent.orchestration.daily_cycle.collect_sources",
                side_effect=RuntimeError("boom"),
            ):
                result = run_daily_intelligence_cycle(
                    DailyCycleOptions(
                        profile="global_safety_alerts",
                        analyze=False,
                        output=root / "insights.jsonl",
                        run_log=root / "daily.jsonl",
                        report_md=root / "brief.md",
                        report_json=root / "brief.json",
                    )
                )

            self.assertFalse(result["ok"])
            self.assertEqual(result["record"]["status"], "failed")
            self.assertIn("boom", result["record"]["error"])
            self.assertTrue((root / "daily.jsonl").exists())


def _pipeline_record():
    return {
        "document": {
            "raw": {
                "document_id": "doc-1",
                "title": "FDA clinical hold",
                "url": "https://example.test/doc-1",
                "source": {"name": "fda_press_releases", "kind": "test"},
            },
            "text": "FDA placed a clinical hold on a clinical program.",
            "checksum": "doc-1",
        },
        "provider": "test",
        "model": "test-model",
        "created_at": "2026-05-01T00:00:00+00:00",
        "insight": {
            "summary": "FDA placed a clinical hold on a clinical program.",
            "events": [{"event_type": "regulatory", "title": "Clinical hold"}],
            "risk_signals": [{"severity": "high", "risk_type": "regulatory"}],
            "needs_human_review": True,
        },
    }


if __name__ == "__main__":
    unittest.main()
