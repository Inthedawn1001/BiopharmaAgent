import unittest
from email.message import Message

from biopharma_agent.collection.feed import FeedFetcher
from biopharma_agent.collection.http_fetcher import HTTPSourceFetcher
from biopharma_agent.collection.registry import SourceRegistry
from biopharma_agent.contracts import SourceRef


class FakeHTTPTransport:
    def get(self, url, headers, timeout):
        message = Message()
        message["Content-Type"] = "text/html; charset=utf-8"
        return 200, message, b"<html><body>hello biotech</body></html>"


class FakeFeedTransport:
    def get(self, url, headers, timeout):
        message = Message()
        message["Content-Type"] = "application/rss+xml; charset=utf-8"
        return 200, message, b"""<?xml version="1.0"?>
        <rss><channel><item>
          <title>FDA update</title>
          <link>https://example.test/fda/1</link>
          <description>Short summary</description>
          <guid>guid-1</guid>
        </item></channel></rss>"""


class FakeDetailTransport:
    def get(self, url, headers, timeout):
        message = Message()
        message["Content-Type"] = "text/html; charset=utf-8"
        return 200, message, (
            b"<html><body><article><h1>FDA update</h1>"
            b"<p>FDA detail page with enough clean article text to verify detail extraction "
            b"and main content cleanup for the feed detail collector.</p></article></body></html>"
        )


class CollectionTest(unittest.TestCase):
    def test_fetch_url_returns_raw_document(self):
        fetcher = HTTPSourceFetcher(transport=FakeHTTPTransport(), respect_robots_txt=False)

        result = fetcher.fetch("https://example.test/news/1")

        self.assertEqual(result.status_code, 200)
        self.assertIn("hello biotech", result.raw_document.raw_text)
        self.assertEqual(result.raw_document.metadata["content_type"], "text/html; charset=utf-8")

    def test_source_registry_roundtrip(self):
        registry = SourceRegistry()
        source = SourceRef(name="exchange", kind="announcement", url="https://example.test")

        registry.register(source)

        self.assertEqual(registry.get("exchange"), source)
        self.assertEqual(registry.list(), [source])

    def test_feed_fetches_clean_detail_documents(self):
        source = SourceRef(name="fda_test", kind="regulatory_feed", url="https://example.test/rss")
        result = FeedFetcher(transport=FakeFeedTransport()).fetch(source)

        documents = result.fetch_detail_documents(
            HTTPSourceFetcher(transport=FakeDetailTransport(), respect_robots_txt=False),
            limit=1,
            clean_html=True,
        )

        self.assertEqual(len(documents), 1)
        self.assertTrue(documents[0].metadata["html_cleaned"])
        self.assertEqual(documents[0].metadata["collector"], "feed_detail")
        self.assertIn("FDA detail page", documents[0].raw_text)


if __name__ == "__main__":
    unittest.main()
