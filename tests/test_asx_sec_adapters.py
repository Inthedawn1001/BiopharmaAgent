import json
import unittest
from email.message import Message

from biopharma_agent.collection.asx import ASXAnnouncementsFetcher, parse_asx_announcements
from biopharma_agent.collection.http_fetcher import HTTPSourceFetcher
from biopharma_agent.collection.sec import SECSubmissionsFetcher, parse_sec_submissions, sec_filing_urls
from biopharma_agent.contracts import SourceRef


ASX_HTML = """
<html><body>
  <table>
    <tr><td>01/05/2026 10:15 AM</td><td><a href="/asxpdf/20260501/pdf/abc123.pdf">Clinical trial update</a></td><td>2 pages</td></tr>
    <tr><td>01/05/2026 11:00 AM</td><td><a href="/asxpdf/20260501/pdf/abc123.pdf">Clinical trial update duplicate</a></td></tr>
    <tr><td>01/05/2026 12:00 PM</td><td><a href="/asxpdf/20260501/pdf/def456.pdf">Capital raising</a></td></tr>
  </table>
</body></html>
"""

SEC_PAYLOAD = {
    "cik": "0000078003",
    "name": "PFIZER INC",
    "filings": {
        "recent": {
            "accessionNumber": ["0000078003-26-000044", "0000078003-26-000045"],
            "filingDate": ["2026-04-27", "2026-04-28"],
            "reportDate": ["2026-04-23", "2026-04-24"],
            "form": ["8-K", "4"],
            "primaryDocument": ["pfe-20260423.htm", "doc4.xml"],
            "primaryDocDescription": ["8-K", ""],
        }
    },
}

SEC_DETAIL = """
<html><body><main>
<h1>Pfizer 8-K</h1>
<p>Pfizer announced a material agreement and regulatory update with enough detail for the
clean text extractor to select this main content block as the primary document body.</p>
</main></body></html>
"""


class FakeASXTransport:
    def get(self, url, headers, timeout):
        message = Message()
        message["Content-Type"] = "text/html; charset=utf-8"
        return 200, message, ASX_HTML.encode("utf-8")


class FakeSECTransport:
    def get(self, url, headers, timeout):
        message = Message()
        message["Content-Type"] = "application/json; charset=utf-8"
        return 200, message, json.dumps(SEC_PAYLOAD).encode("utf-8")


class FakeDetailTransport:
    def get(self, url, headers, timeout):
        message = Message()
        message["Content-Type"] = "text/html; charset=utf-8"
        return 200, message, SEC_DETAIL.encode("utf-8")


class ASXSECAdapterTest(unittest.TestCase):
    def test_asx_parser_deduplicates_and_extracts_links(self):
        items = parse_asx_announcements(ASX_HTML, ticker="CSL")

        self.assertEqual(len(items), 3)
        self.assertEqual(items[0].ticker, "CSL")
        self.assertIn("asxpdf", items[0].url)

    def test_asx_fetcher_returns_empty_success(self):
        source = SourceRef(
            name="asx_test",
            kind="market_announcement_api",
            metadata={"collector": "asx_announcements", "watchlist": ["CSL"]},
        )
        fetcher = ASXAnnouncementsFetcher(transport=FakeASXTransport())

        result = fetcher.fetch(source)
        documents = result.to_raw_documents(limit=1)

        self.assertEqual(result.status_code, 200)
        self.assertEqual(len(result.announcements), 2)
        self.assertEqual(documents[0].metadata["ticker"], "CSL")

    def test_sec_parser_filters_forms_and_builds_urls(self):
        filings = parse_sec_submissions(SEC_PAYLOAD, forms={"8-K", "10-Q"})

        self.assertEqual(len(filings), 1)
        self.assertEqual(filings[0].form, "8-K")
        self.assertIn("/Archives/edgar/data/78003/", filings[0].document_url)

    def test_sec_filing_urls(self):
        filing_url, document_url = sec_filing_urls("0000078003", "0000078003-26-000044", "pfe.htm")

        self.assertTrue(filing_url.endswith("0000078003-26-000044-index.html"))
        self.assertTrue(document_url.endswith("/pfe.htm"))

    def test_sec_fetcher_clean_detail_documents(self):
        source = SourceRef(
            name="sec_test",
            kind="market_regulatory_api",
            metadata={"collector": "sec_submissions", "ciks": ["0000078003"], "forms": ["8-K"]},
        )
        result = SECSubmissionsFetcher(transport=FakeSECTransport()).fetch(source)
        documents = result.to_raw_documents(
            limit=1,
            fetch_details=True,
            clean_html=True,
            fetcher=HTTPSourceFetcher(transport=FakeDetailTransport(), respect_robots_txt=False),
        )

        self.assertEqual(len(documents), 1)
        self.assertTrue(documents[0].metadata["html_cleaned"])
        self.assertIn("Pfizer announced", documents[0].raw_text)


if __name__ == "__main__":
    unittest.main()
