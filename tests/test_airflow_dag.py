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
