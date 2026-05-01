import unittest

from biopharma_agent.analysis.json_utils import parse_json_object


class ParseJsonObjectTest(unittest.TestCase):
    def test_parses_plain_json(self):
        self.assertEqual(parse_json_object('{"summary": "ok"}'), {"summary": "ok"})

    def test_parses_markdown_fenced_json(self):
        self.assertEqual(parse_json_object('```json\n{"summary": "ok"}\n```'), {"summary": "ok"})

    def test_parses_json_inside_extra_text(self):
        self.assertEqual(parse_json_object('Result:\n{"summary": "ok"}\nDone'), {"summary": "ok"})


if __name__ == "__main__":
    unittest.main()

