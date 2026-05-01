import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from biopharma_agent.cli import main
from biopharma_agent.ops.quality_gate import run_quality_gate


class QualityGateTest(unittest.TestCase):
    def test_quality_gate_passes_for_complete_artifacts(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            analysis_path = root / "insights.jsonl"
            brief_path = root / "brief.md"
            state_path = root / "source_state.json"
            analysis_path.write_text(json.dumps(_pipeline_record()) + "\n", encoding="utf-8")
            brief_path.write_text(_brief_markdown(), encoding="utf-8")
            state_path.write_text(
                json.dumps({"sources": {"fda_press_releases": {"last_status": "success"}}}),
                encoding="utf-8",
            )

            result = run_quality_gate(
                analysis_path=analysis_path,
                brief_markdown_path=brief_path,
                source_state_path=state_path,
                require_brief=True,
                require_source_state=True,
            )

            self.assertEqual(result["status"], "pass")
            self.assertEqual(result["summary"]["failed"], 0)

    def test_quality_gate_fails_when_required_brief_is_missing(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            analysis_path = root / "insights.jsonl"
            analysis_path.write_text(json.dumps(_pipeline_record()) + "\n", encoding="utf-8")

            result = run_quality_gate(
                analysis_path=analysis_path,
                brief_markdown_path=root / "missing.md",
                require_brief=True,
            )

            self.assertEqual(result["status"], "fail")
            self.assertIn("brief_present", _failed_check_names(result))

    def test_quality_gate_fails_when_source_failures_exceed_threshold(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            analysis_path = root / "insights.jsonl"
            state_path = root / "source_state.json"
            analysis_path.write_text(json.dumps(_pipeline_record()) + "\n", encoding="utf-8")
            state_path.write_text(
                json.dumps(
                    {
                        "sources": {
                            "fda_press_releases": {"last_status": "success"},
                            "asx_biopharma_announcements": {"last_status": "failed"},
                        }
                    }
                ),
                encoding="utf-8",
            )

            result = run_quality_gate(
                analysis_path=analysis_path,
                source_state_path=state_path,
                require_source_state=True,
                max_failed_sources=0,
            )

            self.assertEqual(result["status"], "fail")
            self.assertIn("failed_sources", _failed_check_names(result))

    def test_quality_gate_cli_returns_zero_for_passing_artifacts(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)
            analysis_path = root / "insights.jsonl"
            brief_path = root / "brief.md"
            state_path = root / "source_state.json"
            analysis_path.write_text(json.dumps(_pipeline_record()) + "\n", encoding="utf-8")
            brief_path.write_text(_brief_markdown(), encoding="utf-8")
            state_path.write_text(json.dumps({"sources": {}}), encoding="utf-8")
            buffer = io.StringIO()

            with redirect_stdout(buffer):
                status = main(
                    [
                        "quality-gate",
                        "--analysis-path",
                        str(analysis_path),
                        "--brief-md",
                        str(brief_path),
                        "--source-state",
                        str(state_path),
                        "--require-brief",
                        "--require-source-state",
                    ]
                )

            self.assertEqual(status, 0)
            self.assertIn("Quality gate pass", buffer.getvalue())

    def test_quality_gate_cli_returns_one_for_failing_artifacts(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            buffer = io.StringIO()

            with redirect_stdout(buffer):
                status = main(
                    [
                        "quality-gate",
                        "--analysis-path",
                        str(Path(temp_dir) / "missing.jsonl"),
                        "--min-records",
                        "1",
                    ]
                )

            self.assertEqual(status, 1)
            self.assertIn("Quality gate fail", buffer.getvalue())


def _failed_check_names(result):
    return {check["name"] for check in result["checks"] if check["status"] == "fail"}


def _brief_markdown():
    return "\n".join(
        [
            "# Biopharma Intelligence Brief",
            "",
            "## Executive Summary",
            "A compact summary.",
            "",
            "## Signals",
            "- Event mix: regulatory (1)",
            "",
            "## Key Developments",
            "No key developments are available.",
            "",
            "## Risk Watchlist",
            "No medium or high risk items found.",
            "",
        ]
    )


def _pipeline_record():
    text = (
        "FDA placed a clinical hold on a clinical program. The sponsor plans to respond with "
        "additional safety data and manufacturing controls. Investors should monitor regulatory "
        "timelines, trial restart requirements, and cash runway impact across the portfolio."
    )
    return {
        "document": {
            "raw": {
                "document_id": "doc-1",
                "title": "FDA clinical hold",
                "url": "https://example.test/doc-1",
                "source": {"name": "fda_press_releases", "kind": "test"},
            },
            "text": text,
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
