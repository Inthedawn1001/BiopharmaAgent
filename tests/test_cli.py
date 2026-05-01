import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

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
