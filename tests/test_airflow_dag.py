import importlib.util
import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch


class AirflowDagTest(unittest.TestCase):
    def test_run_fetch_sources_passes_state_and_incremental_flags(self):
        module = _load_dag_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            run_log = Path(temp_dir) / "runs.jsonl"
            source_state = Path(temp_dir) / "source_state.json"
            _write_success_run(run_log)
            _write_source_state(source_state)
            calls = []

            def fake_run(command, check):
                calls.append(command)
                self.assertTrue(check)

            with patch.dict(
                "os.environ",
                {
                    "BIOPHARMA_AIRFLOW_MODE": "scheduled-fetch",
                    "BIOPHARMA_AIRFLOW_SOURCES": "fda_press_releases biopharma_dive_news",
                    "BIOPHARMA_AIRFLOW_LIMIT": "2",
                    "BIOPHARMA_AIRFLOW_ANALYZE": "1",
                    "BIOPHARMA_AIRFLOW_INCREMENTAL": "1",
                    "BIOPHARMA_AIRFLOW_FETCH_DETAILS": "1",
                    "BIOPHARMA_AIRFLOW_CLEAN_HTML_DETAILS": "1",
                    "BIOPHARMA_AIRFLOW_RUN_LOG": str(run_log),
                    "BIOPHARMA_AIRFLOW_SOURCE_STATE": str(source_state),
                    "BIOPHARMA_AIRFLOW_PYTHON": "python-test",
                },
                clear=True,
            ), patch.object(module.subprocess, "run", side_effect=fake_run):
                summary = module.run_fetch_sources()

        command = calls[0]
        self.assertIn("--state-path", command)
        self.assertIn(str(source_state), command)
        self.assertIn("--incremental", command)
        self.assertIn("--fetch-details", command)
        self.assertIn("--clean-html-details", command)
        self.assertIn("--analyze", command)
        self.assertEqual(summary["status"], "success")
        self.assertEqual(summary["selected"], 1)
        self.assertEqual(summary["source_state_rows"], 1)
        self.assertEqual(summary["source_state_seen"], 1)

    def test_run_fetch_sources_can_use_profile(self):
        module = _load_dag_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            run_log = Path(temp_dir) / "runs.jsonl"
            source_state = Path(temp_dir) / "source_state.json"
            _write_success_run(run_log)
            _write_source_state(source_state)
            calls = []

            def fake_run(command, check):
                calls.append(command)
                self.assertTrue(check)

            with patch.dict(
                "os.environ",
                {
                    "BIOPHARMA_AIRFLOW_MODE": "scheduled-fetch",
                    "BIOPHARMA_AIRFLOW_PROFILE": "global_safety_alerts",
                    "BIOPHARMA_AIRFLOW_SOURCES": "",
                    "BIOPHARMA_AIRFLOW_RUN_LOG": str(run_log),
                    "BIOPHARMA_AIRFLOW_SOURCE_STATE": str(source_state),
                    "BIOPHARMA_AIRFLOW_PYTHON": "python-test",
                },
                clear=True,
            ), patch.object(module.subprocess, "run", side_effect=fake_run):
                module.run_fetch_sources()

        command = calls[0]
        self.assertIn("--profile", command)
        self.assertIn("global_safety_alerts", command)
        self.assertNotIn("--sources", command)

    def test_run_fetch_sources_prefers_explicit_sources_over_profile(self):
        module = _load_dag_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            run_log = Path(temp_dir) / "runs.jsonl"
            source_state = Path(temp_dir) / "source_state.json"
            _write_success_run(run_log)
            _write_source_state(source_state)
            calls = []

            def fake_run(command, check):
                calls.append(command)
                self.assertTrue(check)

            with patch.dict(
                "os.environ",
                {
                    "BIOPHARMA_AIRFLOW_MODE": "scheduled-fetch",
                    "BIOPHARMA_AIRFLOW_PROFILE": "global_safety_alerts",
                    "BIOPHARMA_AIRFLOW_SOURCES": "fda_press_releases",
                    "BIOPHARMA_AIRFLOW_RUN_LOG": str(run_log),
                    "BIOPHARMA_AIRFLOW_SOURCE_STATE": str(source_state),
                    "BIOPHARMA_AIRFLOW_PYTHON": "python-test",
                },
                clear=True,
            ), patch.object(module.subprocess, "run", side_effect=fake_run):
                module.run_fetch_sources()

        command = calls[0]
        self.assertIn("--sources", command)
        self.assertIn("fda_press_releases", command)
        self.assertNotIn("--profile", command)

    def test_run_fetch_sources_can_use_daily_cycle_mode(self):
        module = _load_dag_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            run_log = Path(temp_dir) / "daily_cycles.jsonl"
            source_state = Path(temp_dir) / "source_state.json"
            report_md = Path(temp_dir) / "latest.md"
            report_json = Path(temp_dir) / "latest.json"
            _write_daily_cycle_run(run_log)
            _write_source_state(source_state)
            calls = []

            def fake_run(command, check):
                calls.append(command)
                self.assertTrue(check)

            with patch.dict(
                "os.environ",
                {
                    "BIOPHARMA_AIRFLOW_MODE": "daily-cycle",
                    "BIOPHARMA_AIRFLOW_PROFILE": "core_intelligence",
                    "BIOPHARMA_AIRFLOW_SOURCES": "fda_press_releases",
                    "BIOPHARMA_AIRFLOW_LIMIT": "1",
                    "BIOPHARMA_AIRFLOW_ANALYZE": "0",
                    "BIOPHARMA_AIRFLOW_INCREMENTAL": "1",
                    "BIOPHARMA_AIRFLOW_FETCH_DETAILS": "1",
                    "BIOPHARMA_AIRFLOW_CLEAN_HTML_DETAILS": "1",
                    "BIOPHARMA_AIRFLOW_RUN_LOG": str(run_log),
                    "BIOPHARMA_AIRFLOW_SOURCE_STATE": str(source_state),
                    "BIOPHARMA_AIRFLOW_BRIEF_LIMIT": "25",
                    "BIOPHARMA_AIRFLOW_REPORT_MD": str(report_md),
                    "BIOPHARMA_AIRFLOW_REPORT_JSON": str(report_json),
                    "BIOPHARMA_AIRFLOW_OUTPUT": str(Path(temp_dir) / "insights.jsonl"),
                    "BIOPHARMA_AIRFLOW_PYTHON": "python-test",
                },
                clear=True,
            ), patch.object(module.subprocess, "run", side_effect=fake_run):
                summary = module.run_fetch_sources()

        command = calls[0]
        self.assertIn("daily-cycle", command)
        self.assertIn("--no-analyze", command)
        self.assertIn("--incremental", command)
        self.assertIn("--fetch-details", command)
        self.assertIn("--clean-html-details", command)
        self.assertIn("--brief-limit", command)
        self.assertIn("25", command)
        self.assertIn("--report-md", command)
        self.assertIn(str(report_md), command)
        self.assertIn("--report-json", command)
        self.assertIn(str(report_json), command)
        self.assertIn("--json", command)
        self.assertIn("--sources", command)
        self.assertIn("fda_press_releases", command)
        self.assertNotIn("--profile", command)
        self.assertEqual(summary["job_name"], "daily-intelligence-cycle")
        self.assertEqual(summary["selected"], 2)
        self.assertEqual(summary["analyzed"], 1)
        self.assertEqual(summary["skipped_seen"], 1)
        self.assertEqual(summary["brief_document_count"], 4)
        self.assertEqual(summary["report_md"], "report.md")
        self.assertEqual(summary["report_json"], "report.json")

    def test_run_fetch_sources_rejects_unknown_mode(self):
        module = _load_dag_module()
        with patch.dict("os.environ", {"BIOPHARMA_AIRFLOW_MODE": "unsupported"}, clear=True):
            with self.assertRaises(ValueError):
                module.run_fetch_sources()


def _load_dag_module():
    airflow = types.ModuleType("airflow")
    operators = types.ModuleType("airflow.operators")
    python_module = types.ModuleType("airflow.operators.python")

    class FakeDAG:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

    class FakePythonOperator:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    airflow.DAG = FakeDAG
    python_module.PythonOperator = FakePythonOperator
    with patch.dict(
        sys.modules,
        {
            "airflow": airflow,
            "airflow.operators": operators,
            "airflow.operators.python": python_module,
        },
    ):
        path = Path("infra/airflow/dags/biopharma_fetch_sources.py")
        spec = importlib.util.spec_from_file_location("test_biopharma_fetch_sources", path)
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
    return module


def _write_success_run(path):
    path.write_text(
        json.dumps(
            {
                "status": "success",
                "completed_at": "2026-05-01T00:00:00+00:00",
                "metadata": {"sources": ["fda_press_releases"]},
                "result": [
                    {
                        "source": "fda_press_releases",
                        "selected": 1,
                        "analyzed": 0,
                        "skipped_seen": 0,
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _write_daily_cycle_run(path):
    path.write_text(
        json.dumps(
            {
                "job_name": "daily-intelligence-cycle",
                "run_id": "daily-1",
                "status": "success",
                "completed_at": "2026-05-01T00:00:00+00:00",
                "metadata": {"source_names": ["fda_press_releases"]},
                "result": {
                    "sources": ["fda_press_releases"],
                    "fetch": [
                        {
                            "source": "fda_press_releases",
                            "selected": 2,
                            "analyzed": 1,
                            "skipped_seen": 1,
                        }
                    ],
                    "brief": {
                        "document_count": 4,
                        "summary": "Daily summary",
                        "artifacts": {
                            "markdown": "report.md",
                            "json": "report.json",
                        },
                    },
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _write_source_state(path):
    path.write_text(
        json.dumps(
            {
                "sources": {
                    "fda_press_releases": {
                        "source": "fda_press_releases",
                        "last_status": "success",
                        "last_selected": 1,
                        "seen_count": 1,
                    }
                }
            }
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
