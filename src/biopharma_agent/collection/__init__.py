"""Collection layer."""

from biopharma_agent.collection.feed import FeedFetcher, FeedFetchResult, FeedItem, parse_feed
from biopharma_agent.collection.http_fetcher import HTTPFetchResult, HTTPSourceFetcher
from biopharma_agent.collection.registry import SourceRegistry

__all__ = [
    "FeedFetcher",
    "FeedFetchResult",
    "FeedItem",
    "HTTPFetchResult",
    "HTTPSourceFetcher",
    "SourceRegistry",
    "parse_feed",
]
