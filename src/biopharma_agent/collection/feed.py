"""RSS and Atom feed collection."""

from __future__ import annotations

import hashlib
import re
import socket
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from email.message import Message
from html import unescape
from typing import Any, Protocol

from biopharma_agent.collection.http_fetcher import HTTPSourceFetcher
from biopharma_agent.contracts import RawDocument, SourceRef, utc_now
from biopharma_agent.parsing.text import extract_main_text


class FeedTransport(Protocol):
    def get(self, url: str, headers: dict[str, str], timeout: float) -> tuple[int, Message, bytes]:
        """Fetch a feed URL."""


class UrllibFeedTransport:
    def get(self, url: str, headers: dict[str, str], timeout: float) -> tuple[int, Message, bytes]:
        request = urllib.request.Request(url=url, headers=headers, method="GET")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.headers, response.read()


@dataclass(frozen=True)
class FeedItem:
    title: str
    link: str
    summary: str
    published: str | None
    guid: str | None


@dataclass(frozen=True)
class FeedFetchResult:
    source: SourceRef
    feed_url: str
    status_code: int
    items: list[FeedItem]

    def to_raw_documents(self, limit: int | None = None) -> list[RawDocument]:
        selected = self.items[:limit] if limit is not None else self.items
        return [_feed_item_raw_document(self.source, self.feed_url, item) for item in selected]

    def fetch_detail_documents(
        self,
        fetcher: HTTPSourceFetcher,
        *,
        limit: int | None = None,
        detail_delay_seconds: float = 0.0,
        clean_html: bool = False,
        sleep: Any | None = None,
    ) -> list[RawDocument]:
        selected = self.items[:limit] if limit is not None else self.items
        documents: list[RawDocument] = []
        for index, item in enumerate(selected):
            if detail_delay_seconds > 0 and index > 0 and sleep is not None:
                sleep(detail_delay_seconds)
            try:
                fetched = fetcher.fetch(
                    item.link or self.feed_url,
                    source=self.source,
                    document_id=_stable_document_id(self.source.name, item.guid or item.link or item.title),
                )
            except Exception as exc:
                fallback = _feed_item_raw_document(self.source, self.feed_url, item)
                metadata = dict(fallback.metadata)
                metadata.update(
                    {
                        "collector": "feed_item_fallback",
                        "detail_fetch_failed": True,
                        "detail_fetch_error": str(exc),
                        "detail_url": item.link or self.feed_url,
                    }
                )
                documents.append(
                    RawDocument(
                        source=fallback.source,
                        document_id=fallback.document_id,
                        collected_at=fallback.collected_at,
                        url=fallback.url,
                        title=fallback.title,
                        raw_text=fallback.raw_text,
                        raw_uri=fallback.raw_uri,
                        metadata=metadata,
                    )
                )
                continue
            raw = fetched.raw_document
            metadata = dict(raw.metadata)
            raw_text = raw.raw_text
            metadata.update(
                {
                    "content_type": raw.metadata.get("content_type") or "feed_detail",
                    "collector": "feed_detail",
                    "feed_url": self.feed_url,
                    "feed_title": item.title,
                    "feed_published": item.published,
                    "feed_guid": item.guid,
                    "detail_status_code": fetched.status_code,
                }
            )
            if clean_html:
                extracted = extract_main_text(raw.raw_text or "")
                raw_text = extracted.text
                metadata.update(
                    {
                        "content_type": "text/plain; charset=utf-8",
                        "original_content_type": raw.metadata.get("content_type"),
                        "original_html_length": len(raw.raw_text or ""),
                        "html_cleaned": True,
                        "html_extraction_method": extracted.method,
                        "html_extraction_score": extracted.score,
                    }
                )
            documents.append(
                RawDocument(
                    source=raw.source,
                    document_id=raw.document_id,
                    collected_at=raw.collected_at,
                    url=raw.url,
                    title=item.title or raw.title,
                    raw_text=raw_text,
                    raw_uri=raw.raw_uri,
                    metadata=metadata,
                )
            )
        return documents


@dataclass
class FeedFetcher:
    """Fetch and parse RSS/Atom feeds into RawDocument objects."""

    transport: FeedTransport = UrllibFeedTransport()
    user_agent: str = "biopharma-agent/0.1"
    timeout_seconds: float = 30.0

    def fetch(self, source: SourceRef) -> FeedFetchResult:
        feed_url = source.url
        if not feed_url:
            raise ValueError(f"Source {source.name} does not have a feed URL")
        try:
            status, headers, body = self.transport.get(
                feed_url,
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout_seconds,
            )
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"HTTP {exc.code} while fetching feed {feed_url}") from exc
        except (urllib.error.URLError, socket.timeout) as exc:
            raise RuntimeError(f"Failed to fetch feed {feed_url}: {exc}") from exc

        charset = headers.get_content_charset() or "utf-8"
        xml_text = body.decode(charset, errors="replace")
        return FeedFetchResult(
            source=source,
            feed_url=feed_url,
            status_code=status,
            items=parse_feed(xml_text),
        )


def parse_feed(xml_text: str) -> list[FeedItem]:
    root = ET.fromstring(xml_text)
    if _strip_ns(root.tag) == "rss":
        return _parse_rss(root)
    if _strip_ns(root.tag) == "feed":
        return _parse_atom(root)
    channel = root.find("channel")
    if channel is not None:
        return _parse_rss(root)
    raise ValueError(f"Unsupported feed root: {root.tag}")


def _parse_rss(root: ET.Element) -> list[FeedItem]:
    channel = root.find("channel")
    if channel is None:
        return []
    items: list[FeedItem] = []
    for item in channel.findall("item"):
        title = _clean_text(_find_text(item, "title"))
        summary = _clean_text(_find_text(item, "description") or _find_text(item, "encoded"))
        link = _clean_text(_find_text(item, "link"))
        published = _clean_text(_find_text(item, "pubDate")) or None
        guid = _clean_text(_find_text(item, "guid")) or None
        items.append(FeedItem(title=title, link=link, summary=summary, published=published, guid=guid))
    return items


def _parse_atom(root: ET.Element) -> list[FeedItem]:
    items: list[FeedItem] = []
    for entry in [child for child in root if _strip_ns(child.tag) == "entry"]:
        title = _clean_text(_find_text(entry, "title"))
        summary = _clean_text(_find_text(entry, "summary") or _find_text(entry, "content"))
        link = ""
        for child in entry:
            if _strip_ns(child.tag) == "link":
                link = child.attrib.get("href", "")
                if link:
                    break
        published = _clean_text(_find_text(entry, "published") or _find_text(entry, "updated")) or None
        guid = _clean_text(_find_text(entry, "id")) or None
        items.append(FeedItem(title=title, link=link, summary=summary, published=published, guid=guid))
    return items


def _find_text(element: ET.Element, local_name: str) -> str:
    for child in element.iter():
        if _strip_ns(child.tag) == local_name:
            return child.text or ""
    return ""


def _feed_item_raw_document(source: SourceRef, feed_url: str, item: FeedItem) -> RawDocument:
    text = "\n\n".join(part for part in [item.title, item.summary, item.link] if part)
    return RawDocument(
        source=source,
        document_id=_stable_document_id(source.name, item.guid or item.link or item.title),
        collected_at=utc_now(),
        url=item.link or feed_url,
        title=item.title,
        raw_text=text,
        metadata={
            "content_type": "feed_item",
            "collector": "feed_item",
            "feed_url": feed_url,
            "published": item.published,
            "guid": item.guid,
        },
    )


def _strip_ns(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _clean_text(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = unescape(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _stable_document_id(source_name: str, key: str) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    safe_source = re.sub(r"[^a-zA-Z0-9_-]+", "-", source_name.lower()).strip("-")
    return f"{safe_source}-{digest}"
