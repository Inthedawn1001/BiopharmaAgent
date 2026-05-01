import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import patch

from biopharma_agent.cli import _fetch_and_optionally_analyze_html_sources, main
from biopharma_agent.collection.html_listing import HTMLListingFetcher, extract_listing_links
from biopharma_agent.collection.http_fetcher import HTTPSourceFetcher
from biopharma_agent.contracts import SourceRef
from biopharma_agent.sources import get_default_source, list_default_sources


HTML_FIXTURE = """
<html>
  <body>
    <a href="/news/20260430-biotech-funding.aspx">Biotech funding advances</a>
    <a href="/whitepaper/vendor.aspx">Vendor whitepaper</a>
    <a href="https://example.test/news/20260430-biotech-funding.aspx">Duplicate title</a>
    <a href="/news/20260430-fda-approval.aspx">FDA approval update</a>
  </body>
</html>
"""

DETAIL_FIXTURE = """
<html>
  <body>
    <article>
      <h1>Biotech funding advances</h1>
      <p>Detailed financing story with clinical milestones and enough added context to pass
      the main content extraction threshold for clean detail tests in the feed and listing adapters.</p>
    </article>
  </body>
</html>
"""


class FakeHTMLTransport:
    def get(self, url, headers, timeout):
        message = Message()
        message["Content-Type"] = "text/html; charset=utf-8"
        body = DETAIL_FIXTURE if "/news/" in url else HTML_FIXTURE
        return 200, message, body.encode("utf-8")


class HTMLListingTest(unittest.TestCase):
    def test_extract_listing_links_filters_and_deduplicates(self):
        links = extract_listing_links(
            HTML_FIXTURE,
            base_url="https://example.test/listing",
            include_url_patterns=[r"example\.test/news/"],
            exclude_url_patterns=[r"whitepaper"],
            limit=10,
        )

        self.assertEqual(len(links), 2)
        self.assertEqual(links[0].title, "Biotech funding advances")
        self.assertEqual(links[0].url, "https://example.test/news/20260430-biotech-funding.aspx")

    def test_html_listing_fetcher_returns_raw_documents(self):
        source = SourceRef(
            name="html_source",
            kind="industry_news_html",
            url="https://example.test/listing",
            metadata={
                "collector": "html_listing",
                "html_listing": {
                    "include_url_patterns": [r"example\.test/news/"],
                    "exclude_url_patterns": [r"whitepaper"],
                    "max_links": 5,
                },
            },
        )
        fetcher = HTMLListingFetcher(
            HTTPSourceFetcher(transport=FakeHTMLTransport(), respect_robots_txt=False)
        )

        result = fetcher.fetch(source)
        documents = result.to_raw_documents(limit=1)

        self.assertEqual(result.status_code, 200)
        self.assertEqual(len(result.links), 2)
        self.assertEqual(documents[0].source.name, "html_source")
        self.assertIn("Biotech funding advances", documents[0].raw_text)

    def test_html_listing_fetches_detail_documents(self):
        source = SourceRef(
            name="html_source",
            kind="industry_news_html",
            url="https://example.test/listing",
            metadata={
                "collector": "html_listing",
                "html_listing": {
                    "include_url_patterns": [r"example\.test/news/"],
                    "exclude_url_patterns": [r"whitepaper"],
                    "max_links": 5,
                },
            },
        )
        http_fetcher = HTTPSourceFetcher(transport=FakeHTMLTransport(), respect_robots_txt=False)
        result = HTMLListingFetcher(http_fetcher).fetch(source)

        documents = result.fetch_detail_documents(http_fetcher, limit=1)

        self.assertEqual(len(documents), 1)
        self.assertEqual(documents[0].metadata["collector"], "html_listing_detail")
        self.assertEqual(documents[0].metadata["listing_title"], "Biotech funding advances")
        self.assertIn("Detailed financing story", documents[0].raw_text)

    def test_html_listing_fetches_clean_detail_documents(self):
        source = SourceRef(
            name="html_source",
            kind="industry_news_html",
            url="https://example.test/listing",
            metadata={
                "collector": "html_listing",
                "html_listing": {
                    "include_url_patterns": [r"example\.test/news/"],
                    "exclude_url_patterns": [r"whitepaper"],
                    "max_links": 5,
                },
            },
        )
        http_fetcher = HTTPSourceFetcher(transport=FakeHTMLTransport(), respect_robots_txt=False)
        result = HTMLListingFetcher(http_fetcher).fetch(source)

        documents = result.fetch_detail_documents(http_fetcher, limit=1, clean_html=True)

        self.assertTrue(documents[0].metadata["html_cleaned"])
        self.assertEqual(documents[0].metadata["content_type"], "text/plain; charset=utf-8")
        self.assertIn("Detailed financing story", documents[0].raw_text)
        self.assertNotIn("<article>", documents[0].raw_text)

    def test_default_html_sources_are_listed(self):
        html_sources = [
            source.name
            for source in list_default_sources()
            if source.metadata.get("collector") == "html_listing"
        ]

        self.assertIn("news_medical_life_sciences", html_sources)
        self.assertFalse(get_default_source("news_medical_life_sciences").metadata["enabled"])
        self.assertEqual(
            get_default_source("investegate_announcements").metadata["category"],
            "market_announcement",
        )
        self.assertEqual(
            get_default_source("investegate_announcements").url,
            "https://www.investegate.co.uk/today-announcements",
        )

    def test_cli_html_fetch_summary(self):
        source = SourceRef(
            name="html_source",
            kind="industry_news_html",
            url="https://example.test/listing",
            metadata={
                "collector": "html_listing",
                "category": "life_science_news",
                "priority": 45,
                "request_delay_seconds": 0,
                "html_listing": {
                    "include_url_patterns": [r"example\.test/news/"],
                    "exclude_url_patterns": [r"whitepaper"],
                    "max_links": 5,
                },
            },
        )
        fetcher = HTMLListingFetcher(
            HTTPSourceFetcher(transport=FakeHTMLTransport(), respect_robots_txt=False)
        )
        with patch("biopharma_agent.collection.runner.HTMLListingFetcher", return_value=fetcher):
            summary = _fetch_and_optionally_analyze_html_sources(
                sources=[source],
                limit=1,
                analyze=False,
                provider=None,
                archive_dir=Path("unused/raw"),
                output=Path("unused/insights.jsonl"),
                graph_dir=Path("unused/graph"),
                no_graph=True,
                update_state=False,
            )

        self.assertEqual(summary[0]["source"], "html_source")
        self.assertEqual(summary[0]["fetched"], 2)
        self.assertEqual(summary[0]["selected"], 1)
        self.assertEqual(summary[0]["items"][0]["title"], "Biotech funding advances")

    def test_cli_html_fetch_summary_with_details(self):
        source = SourceRef(
            name="html_source",
            kind="industry_news_html",
            url="https://example.test/listing",
            metadata={
                "collector": "html_listing",
                "category": "life_science_news",
                "priority": 45,
                "request_delay_seconds": 0,
                "html_listing": {
                    "include_url_patterns": [r"example\.test/news/"],
                    "exclude_url_patterns": [r"whitepaper"],
                    "max_links": 5,
                },
            },
        )
        fetcher = HTMLListingFetcher(
            HTTPSourceFetcher(transport=FakeHTMLTransport(), respect_robots_txt=False)
        )
        with patch("biopharma_agent.collection.runner.HTMLListingFetcher", return_value=fetcher), patch(
            "biopharma_agent.collection.runner.HTTPSourceFetcher",
            return_value=HTTPSourceFetcher(transport=FakeHTMLTransport(), respect_robots_txt=False),
        ):
            summary = _fetch_and_optionally_analyze_html_sources(
                sources=[source],
                limit=1,
                analyze=False,
                provider=None,
                archive_dir=Path("unused/raw"),
                output=Path("unused/insights.jsonl"),
                graph_dir=Path("unused/graph"),
                no_graph=True,
                fetch_details=True,
                detail_delay_seconds=0,
                clean_html_details=True,
                update_state=False,
            )

        self.assertEqual(summary[0]["details_fetched"], 1)
        self.assertTrue(summary[0]["clean_html_details"])
        self.assertEqual(summary[0]["selected"], 1)

    def test_main_fetch_html_source_passes_detail_flags(self):
        with patch("biopharma_agent.cli._fetch_and_optionally_analyze_html_sources") as helper:
            helper.return_value = []
            status = main(
                [
                    "fetch-html-source",
                    "investegate_announcements",
                    "--limit",
                    "1",
                    "--fetch-details",
                    "--clean-html-details",
                    "--detail-delay-seconds",
                    "0",
                ]
            )

        self.assertEqual(status, 0)
        self.assertTrue(helper.call_args.kwargs["fetch_details"])
        self.assertTrue(helper.call_args.kwargs["clean_html_details"])
        self.assertEqual(helper.call_args.kwargs["detail_delay_seconds"], 0)


if __name__ == "__main__":
    unittest.main()
