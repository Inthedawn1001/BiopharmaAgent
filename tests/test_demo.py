import tempfile
import unittest
from pathlib import Path

from biopharma_agent.demo import seed_demo_data
from biopharma_agent.web.api import list_jsonl


class DemoTest(unittest.TestCase):
    def test_seed_demo_data(self):
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as temp_dir:
            root = Path(temp_dir)

            paths = seed_demo_data(
                output=root / "insights.jsonl",
                feedback_output=root / "feedback.jsonl",
            )

            self.assertTrue(Path(paths["insights"]).exists())
            self.assertTrue(Path(paths["feedback"]).exists())
            self.assertEqual(list_jsonl(paths["insights"])["count"], 1)


if __name__ == "__main__":
    unittest.main()

