import unittest

from biopharma_agent.contracts import RawDocument, SourceRef
from biopharma_agent.parsing.text import extract_main_text, parse_raw_document


class ParsingTest(unittest.TestCase):
    def test_plain_text_parser_detects_chinese(self):
        raw = RawDocument(
            source=SourceRef(name="test", kind="manual"),
            document_id="1",
            raw_text="测试生物宣布完成B轮融资。",
        )

        parsed = parse_raw_document(raw)

        self.assertEqual(parsed.language, "zh")
        self.assertEqual(parsed.metadata["parser"], "plain_text")
        self.assertTrue(parsed.checksum)

    def test_html_parser_removes_script_text(self):
        raw = RawDocument(
            source=SourceRef(name="test", kind="manual"),
            document_id="1",
            raw_text="<html><script>bad()</script><body><p>Hello market</p></body></html>",
        )

        parsed = parse_raw_document(raw)

        self.assertIn("Hello market", parsed.text)
        self.assertNotIn("bad", parsed.text)
        self.assertEqual(parsed.metadata["parser"], "html_text")

    def test_html_parser_prefers_article_text(self):
        raw = RawDocument(
            source=SourceRef(name="test", kind="manual"),
            document_id="1",
            raw_text=(
                "<html><body><nav>Menu Link</nav><article>"
                "<h1>Clinical update</h1><p>This detailed clinical update has enough text "
                "to be treated as the main body of the document for extraction.</p>"
                "</article><footer>Footer text</footer></body></html>"
            ),
        )

        parsed = parse_raw_document(raw)

        self.assertIn("Clinical update", parsed.text)
        self.assertNotIn("Menu Link", parsed.text)
        self.assertEqual(parsed.metadata["extraction_method"], "semantic_container")
        self.assertGreater(parsed.metadata["extraction_score"], 80)

    def test_extract_main_text_uses_density_fallback(self):
        extracted = extract_main_text(
            "<html><body><div>Short</div><div>"
            "This is a longer block of market announcement text with enough words "
            "to be scored as the best density block for extraction.</div></body></html>"
        )

        self.assertEqual(extracted.method, "density_block")
        self.assertIn("market announcement", extracted.text)
        self.assertGreater(extracted.score, 100)


if __name__ == "__main__":
    unittest.main()
