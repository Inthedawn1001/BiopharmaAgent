import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from biopharma_agent.ops.diagnostics import diagnose_environment
from biopharma_agent.web import api


class DiagnosticsTest(unittest.TestCase):
    def test_diagnostics_is_secret_safe(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir, patch.dict(
            os.environ,
            {
                "BIOPHARMA_LLM_PROVIDER": "custom",
                "BIOPHARMA_LLM_BASE_URL": "https://api.deepseek.com/v1",
                "BIOPHARMA_LLM_API_KEY": "sk-test-secret",
                "BIOPHARMA_LLM_MODEL": "deepseek-chat",
            },
            clear=False,
        ):
            data = diagnose_environment(temp_dir)

            self.assertTrue(data["checks"]["llm"]["has_api_key"])
            self.assertNotIn("sk-test-secret", repr(data))

    def test_diagnostics_warns_when_llm_key_missing(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir, patch.dict(
            os.environ,
            {
                "BIOPHARMA_LLM_PROVIDER": "openai",
                "BIOPHARMA_LLM_API_KEY": "",
            },
            clear=False,
        ):
            data = diagnose_environment(temp_dir)

            self.assertEqual(data["checks"]["llm"]["status"], "warning")
            self.assertIn("BIOPHARMA_LLM_API_KEY", data["checks"]["llm"]["issues"][0])

    def test_diagnostics_accepts_smoke_provider_without_key(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir, patch.dict(
            os.environ,
            {
                "BIOPHARMA_LLM_PROVIDER": "smoke",
                "BIOPHARMA_LLM_API_KEY": "",
                "BIOPHARMA_LLM_MODEL": "smoke-model",
            },
            clear=False,
        ):
            data = diagnose_environment(temp_dir)

            self.assertEqual(data["checks"]["llm"]["status"], "ok")
            self.assertFalse(data["checks"]["llm"]["api_key_required"])

    def test_api_diagnostics_returns_source_counts(self):
        data = api.diagnostics()

        self.assertIn("checks", data)
        self.assertIn("graph", data["checks"])
        self.assertGreaterEqual(data["checks"]["sources"]["enabled"], 1)
        self.assertIn("sec_biopharma_filings", data["checks"]["sources"]["enabled_sources"])

    def test_diagnostics_warns_when_neo4j_is_missing_uri(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir, patch.dict(
            os.environ,
            {
                "BIOPHARMA_GRAPH_BACKEND": "neo4j",
                "BIOPHARMA_NEO4J_URI": "",
            },
            clear=False,
        ):
            data = diagnose_environment(temp_dir)

            self.assertEqual(data["checks"]["graph"]["status"], "warning")
            self.assertIn("BIOPHARMA_NEO4J_URI", " ".join(data["checks"]["graph"]["issues"]))


if __name__ == "__main__":
    unittest.main()
