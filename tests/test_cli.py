import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from biopharma_agent.cli import main


class CliTest(unittest.TestCase):
    def test_source_report_prints_markdown(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            buffer = io.StringIO()

            with redirect_stdout(buffer):
                status = main(
                    [
                        "source-report",
                        "--state-path",
                        str(Path(temp_dir) / "source_state.json"),
                        "--run-log",
                        str(Path(temp_dir) / "runs.jsonl"),
                    ]
                )

            self.assertEqual(status, 0)
            self.assertIn("# Biopharma Agent Source Health Report", buffer.getvalue())

    def test_source_report_can_print_json(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            buffer = io.StringIO()

            with redirect_stdout(buffer):
                status = main(
                    [
                        "source-report",
                        "--json",
                        "--state-path",
                        str(Path(temp_dir) / "source_state.json"),
                        "--run-log",
                        str(Path(temp_dir) / "runs.jsonl"),
                    ]
                )

            self.assertEqual(status, 0)
            decoded = json.loads(buffer.getvalue())
            self.assertIn("markdown", decoded)
            self.assertIn("summary", decoded)

    def test_intelligence_brief_prints_markdown(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            path = Path(temp_dir) / "insights.jsonl"
            path.write_text(json.dumps(_pipeline_record()) + "\n", encoding="utf-8")
            buffer = io.StringIO()

            with redirect_stdout(buffer):
                status = main(["intelligence-brief", "--input", str(path)])

            self.assertEqual(status, 0)
            self.assertIn("# Biopharma Intelligence Brief", buffer.getvalue())

    def test_list_source_profiles_prints_profiles(self):
        buffer = io.StringIO()

        with redirect_stdout(buffer):
            status = main(["list-source-profiles"])

        self.assertEqual(status, 0)
        decoded = json.loads(buffer.getvalue())
        names = {item["name"] for item in decoded}
        self.assertIn("core_intelligence", names)
        self.assertIn("global_safety_alerts", names)

    def test_fetch_sources_uses_profile_when_sources_omitted(self):
        buffer = io.StringIO()
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir, patch(
            "biopharma_agent.cli._fetch_and_optionally_analyze_sources",
            return_value=[{"source": "fda_medwatch"}, {"source": "mhra_drug_device_alerts"}],
        ) as helper:
            with redirect_stdout(buffer):
                status = main(
                    [
                        "fetch-sources",
                        "--profile",
                        "global_safety_alerts",
                        "--limit",
                        "1",
                        "--output",
                        str(Path(temp_dir) / "insights.jsonl"),
                        "--archive-dir",
                        str(Path(temp_dir) / "raw"),
                        "--graph-dir",
                        str(Path(temp_dir) / "graph"),
                        "--no-update-state",
                    ]
                )

        self.assertEqual(status, 0)
        source_names = [source.name for source in helper.call_args.kwargs["sources"]]
        self.assertEqual(source_names, ["fda_medwatch", "mhra_drug_device_alerts"])

    def test_fetch_sources_explicit_sources_override_profile(self):
        buffer = io.StringIO()
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir, patch(
            "biopharma_agent.cli._fetch_and_optionally_analyze_sources",
            return_value=[{"source": "fda_press_releases"}],
        ) as helper:
            with redirect_stdout(buffer):
                status = main(
                    [
                        "fetch-sources",
                        "--profile",
                        "global_safety_alerts",
                        "--sources",
                        "fda_press_releases",
                        "--limit",
                        "1",
                        "--output",
                        str(Path(temp_dir) / "insights.jsonl"),
                        "--archive-dir",
                        str(Path(temp_dir) / "raw"),
                        "--graph-dir",
                        str(Path(temp_dir) / "graph"),
                        "--no-update-state",
                    ]
                )

        self.assertEqual(status, 0)
        source_names = [source.name for source in helper.call_args.kwargs["sources"]]
        self.assertEqual(source_names, ["fda_press_releases"])


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
