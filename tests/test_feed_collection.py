import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from biopharma_agent.cli import _fetch_and_optionally_analyze_sources, run_fetch_sources_job
from biopharma_agent.collection.feed import FeedFetcher, FeedFetchResult, FeedItem, parse_feed
from biopharma_agent.collection.runner import CollectionOptions, collect_source
from biopharma_agent.contracts import SourceRef
from biopharma_agent.orchestration.source_state import LocalSourceStateStore
from biopharma_agent.sources import get_default_source, list_default_sources


RSS_FIXTURE = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>Test Feed</title>
    <item>
      <title>FDA approves test therapy</title>
      <link>https://example.test/news/1</link>
      <description><![CDATA[<p>Approval details</p>]]></description>
      <pubDate>Thu, 30 Apr 2026 10:00:00 GMT</pubDate>
      <guid>item-1</guid>
    </item>
  </channel>
</rss>
"""

ATOM_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <id>tag:www.gov.uk,2005:/drug-device-alerts</id>
  <title>Alerts, recalls and safety information: medicines and medical devices</title>
  <updated>2026-04-30T17:08:36+01:00</updated>
  <entry>
    <id>tag:www.gov.uk,2005:/drug-device-alerts/mhra-safety-roundup-april-2026</id>
    <updated>2026-04-29T14:02:41+01:00</updated>
    <link rel="alternate" type="text/html" href="https://www.gov.uk/drug-device-alerts/mhra-safety-roundup-april-2026"/>
    <title>MHRA Safety Roundup: April 2026</title>
    <summary type="html">Summary of the latest safety advice for medicines and medical device users</summary>
  </entry>
</feed>
"""


class FakeFeedTransport:
    def get(self, url, headers, timeout):
        from email.message import Message

        headers_obj = Message()
        headers_obj["Content-Type"] = "application/rss+xml; charset=utf-8"
        return 200, headers_obj, RSS_FIXTURE.encode("utf-8")


class FeedCollectionTest(unittest.TestCase):
    def test_parse_rss(self):
        items = parse_feed(RSS_FIXTURE)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "FDA approves test therapy")
        self.assertEqual(items[0].summary, "Approval details")

    def test_parse_atom(self):
        items = parse_feed(ATOM_FIXTURE)

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "MHRA Safety Roundup: April 2026")
        self.assertEqual(items[0].published, "2026-04-29T14:02:41+01:00")
        self.assertEqual(items[0].guid, "tag:www.gov.uk,2005:/drug-device-alerts/mhra-safety-roundup-april-2026")
        self.assertEqual(items[0].link, "https://www.gov.uk/drug-device-alerts/mhra-safety-roundup-april-2026")

    def test_feed_fetcher_to_raw_documents(self):
        source = SourceRef(name="test_feed", kind="regulatory_feed", url="https://example.test/rss")
        fetcher = FeedFetcher(transport=FakeFeedTransport())

        result = fetcher.fetch(source)
        documents = result.to_raw_documents(limit=1)

        self.assertEqual(result.status_code, 200)
        self.assertEqual(documents[0].source.name, "test_feed")
        self.assertIn("FDA approves test therapy", documents[0].raw_text)

    def test_run_fetch_sources_job_fetches_without_analysis(self):
        source = SourceRef(name="fda_press_releases", kind="regulatory_feed", url="https://example.test/rss")
        fetch_result = FeedFetchResult(
            source=source,
            feed_url=source.url or "",
            status_code=200,
            items=[
                FeedItem(
                    title="FDA approves test therapy",
                    link="https://example.test/news/1",
                    summary="Approval details",
                    published="Thu, 30 Apr 2026 10:00:00 GMT",
                    guid="item-1",
                )
            ],
        )

        with patch("biopharma_agent.collection.runner.FeedFetcher") as fetcher_class:
            fetcher_class.return_value.fetch.return_value = fetch_result
            summary = run_fetch_sources_job(
                source_names=["fda_press_releases"],
                limit=1,
                analyze=False,
                archive_dir=Path("unused/raw"),
                output=Path("unused/insights.jsonl"),
                graph_dir=Path("unused/graph"),
                no_graph=True,
                update_state=False,
            )

        self.assertEqual(summary[0]["source"], "fda_press_releases")
        self.assertEqual(summary[0]["selected"], 1)
        self.assertEqual(summary[0]["analyzed"], 0)
        self.assertEqual(summary[0]["category"], "regulatory_press_release")

    def test_default_sources_can_filter_by_category_and_are_priority_sorted(self):
        regulatory = list_default_sources(category="regulatory_press_release")

        self.assertEqual([source.name for source in regulatory], ["fda_press_releases"])
        priorities = [int(source.metadata["priority"]) for source in list_default_sources()]
        self.assertEqual(priorities, sorted(priorities))
        self.assertEqual(get_default_source("biospace_business").metadata["publisher"], "BioSpace")

    def test_mhra_drug_device_alerts_source_metadata(self):
        source = get_default_source("mhra_drug_device_alerts")

        self.assertEqual(source.kind, "regulatory_feed")
        self.assertEqual(source.url, "https://www.gov.uk/drug-device-alerts.atom")
        self.assertEqual(source.metadata["authority"], "MHRA")
        self.assertEqual(source.metadata["region"], "UK")
        self.assertEqual(source.metadata["category"], "safety_alert")
        self.assertTrue(source.metadata.get("enabled", True))

    def test_fetch_summary_includes_source_metadata_and_respects_delay(self):
        source = SourceRef(
            name="custom",
            kind="industry_news_feed",
            url="https://example.test/rss",
            metadata={
                "category": "custom_category",
                "priority": 77,
                "request_delay_seconds": 0.01,
            },
        )
        fetch_result = FeedFetchResult(
            source=source,
            feed_url=source.url or "",
            status_code=200,
            items=[
                FeedItem(
                    title="News",
                    link="https://example.test/news",
                    summary="Summary",
                    published=None,
                    guid="item",
                )
            ],
        )

        with patch("biopharma_agent.collection.runner.time.sleep") as sleep, patch(
            "biopharma_agent.collection.runner.FeedFetcher"
        ) as fetcher_class:
            fetcher_class.return_value.fetch.return_value = fetch_result
            summary = _fetch_and_optionally_analyze_sources(
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

        sleep.assert_called_once_with(0.01)
        self.assertEqual(summary[0]["kind"], "industry_news_feed")
        self.assertEqual(summary[0]["category"], "custom_category")
        self.assertEqual(summary[0]["priority"], 77)

    def test_collect_source_filters_seen_documents_when_incremental(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            state_path = Path(temp_dir) / "source_state.json"
            source = SourceRef(
                name="fda_press_releases",
                kind="regulatory_feed",
                url="https://example.test/rss",
            )
            fetch_result = FeedFetchResult(
                source=source,
                feed_url=source.url or "",
                status_code=200,
                items=[
                    FeedItem(
                        title="Existing update",
                        link="https://example.test/news/1",
                        summary="Already seen",
                        published=None,
                        guid="item-1",
                    ),
                    FeedItem(
                        title="New update",
                        link="https://example.test/news/2",
                        summary="New item",
                        published=None,
                        guid="item-2",
                    ),
                ],
            )
            store = LocalSourceStateStore(state_path)
            first_doc = fetch_result.to_raw_documents(limit=1)[0]
            store.record_success(
                source,
                started_at=first_doc.collected_at,
                completed_at=first_doc.collected_at,
                summary={"selected": 1},
                documents=[first_doc],
            )

            with patch("biopharma_agent.collection.runner.FeedFetcher") as fetcher_class:
                fetcher_class.return_value.fetch.return_value = fetch_result
                summary = collect_source(
                    source=source,
                    options=CollectionOptions(
                        limit=2,
                        incremental=True,
                        state_path=state_path,
                        update_state=True,
                    ),
                )

            self.assertEqual(summary["fetched"], 2)
            self.assertEqual(summary["selected"], 1)
            self.assertEqual(summary["skipped_seen"], 1)
            self.assertTrue(summary["incremental"])
            self.assertEqual(LocalSourceStateStore(state_path).get_record(source.name)["seen_count"], 2)


if __name__ == "__main__":
    unittest.main()
