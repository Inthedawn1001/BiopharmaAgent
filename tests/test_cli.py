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


if __name__ == "__main__":
    unittest.main()
