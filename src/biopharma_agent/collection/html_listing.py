"""HTML listing-page collection adapters."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

from biopharma_agent.collection.http_fetcher import HTTPSourceFetcher
from biopharma_agent.contracts import RawDocument, SourceRef, utc_now
from biopharma_agent.parsing.text import extract_main_text


@dataclass(frozen=True)
class HTMLLink:
    title: str
    url: str


@dataclass(frozen=True)
class HTMLListingResult:
    source: SourceRef
    listing_url: str
    status_code: int
    links: list[HTMLLink]

    def to_raw_documents(self, limit: int | None = None) -> list[RawDocument]:
        selected = self.links[:limit] if limit is not None else self.links
        documents: list[RawDocument] = []
        for link in selected:
            documents.append(
                RawDocument(
                    source=self.source,
                    document_id=_stable_document_id(self.source.name, link.url),
                    collected_at=utc_now(),
                    url=link.url,
                    title=link.title,
                    raw_text="\n\n".join(part for part in [link.title, link.url] if part),
                    metadata={
                        "content_type": "html_listing_item",
                        "listing_url": self.listing_url,
                    },
                )
            )
        return documents

    def fetch_detail_documents(
        self,
        fetcher: HTTPSourceFetcher,
        *,
        limit: int | None = None,
        detail_delay_seconds: float = 0.0,
        clean_html: bool = False,
        sleep: Any | None = None,
    ) -> list[RawDocument]:
        selected = self.links[:limit] if limit is not None else self.links
        documents: list[RawDocument] = []
        for index, link in enumerate(selected):
            if detail_delay_seconds > 0 and index > 0 and sleep is not None:
                sleep(detail_delay_seconds)
            fetched = fetcher.fetch(
                link.url,
                source=self.source,
                document_id=_stable_document_id(self.source.name, link.url),
            )
            raw = fetched.raw_document
            metadata = dict(raw.metadata)
            raw_text = raw.raw_text
            metadata.update(
                {
                    "content_type": raw.metadata.get("content_type") or "html_detail",
                    "collector": "html_listing_detail",
                    "listing_url": self.listing_url,
                    "listing_title": link.title,
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
                    title=link.title or raw.title,
                    raw_text=raw_text,
                    raw_uri=raw.raw_uri,
                    metadata=metadata,
                )
            )
        return documents


@dataclass
class HTMLListingFetcher:
    """Fetch an HTML listing page and extract article/announcement links."""

    fetcher: HTTPSourceFetcher | None = None

    def fetch(self, source: SourceRef) -> HTMLListingResult:
        listing_url = source.url
        if not listing_url:
            raise ValueError(f"Source {source.name} does not have a listing URL")
        fetcher = self.fetcher or HTTPSourceFetcher(
            respect_robots_txt=bool(source.metadata.get("respect_robots_txt", True))
        )
        fetched = fetcher.fetch(listing_url, source=source)
        rules = source.metadata.get("html_listing") if isinstance(source.metadata, dict) else {}
        links = extract_listing_links(
            fetched.raw_document.raw_text or "",
            base_url=listing_url,
            include_url_patterns=_list_value(rules, "include_url_patterns"),
            exclude_url_patterns=_list_value(rules, "exclude_url_patterns"),
            title_keywords=_list_value(rules, "title_keywords"),
            limit=int(rules.get("max_links", 50)) if isinstance(rules, dict) else 50,
        )
        return HTMLListingResult(
            source=source,
            listing_url=listing_url,
            status_code=fetched.status_code,
            links=links,
        )


def extract_listing_links(
    html: str,
    *,
    base_url: str,
    include_url_patterns: list[str] | None = None,
    exclude_url_patterns: list[str] | None = None,
    title_keywords: list[str] | None = None,
    limit: int = 50,
) -> list[HTMLLink]:
    parser = _AnchorExtractor(base_url)
    parser.feed(html)
    links: list[HTMLLink] = []
    seen: set[str] = set()
    for link in parser.links:
        if link.url in seen:
            continue
        if not _matches_patterns(link.url, include_url_patterns or [], default=True):
            continue
        if _matches_patterns(link.url, exclude_url_patterns or [], default=False):
            continue
        if title_keywords and not _matches_keywords(link.title, title_keywords):
            continue
        seen.add(link.url)
        links.append(link)
        if len(links) >= limit:
            break
    return links


class _AnchorExtractor(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.links: list[HTMLLink] = []
        self._current_href: str | None = None
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower_tag = tag.lower()
        if lower_tag in {"script", "style", "noscript"}:
            self._skip_depth += 1
            return
        if lower_tag == "a":
            attrs_dict = {key.lower(): value for key, value in attrs if value is not None}
            href = attrs_dict.get("href", "")
            if href and not href.startswith(("#", "javascript:", "mailto:")):
                self._current_href = urljoin(self.base_url, href)
                self._parts = []

    def handle_endtag(self, tag: str) -> None:
        lower_tag = tag.lower()
        if lower_tag in {"script", "style", "noscript"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if lower_tag == "a" and self._current_href:
            title = _clean_text(" ".join(self._parts))
            if title:
                self.links.append(HTMLLink(title=title, url=self._current_href))
            self._current_href = None
            self._parts = []

    def handle_data(self, data: str) -> None:
        if self._current_href and not self._skip_depth and data.strip():
            self._parts.append(data.strip())


def _list_value(rules: Any, key: str) -> list[str]:
    if not isinstance(rules, dict):
        return []
    value = rules.get(key, [])
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def _matches_patterns(value: str, patterns: list[str], *, default: bool) -> bool:
    if not patterns:
        return default
    return any(re.search(pattern, value) for pattern in patterns)


def _matches_keywords(title: str, keywords: list[str]) -> bool:
    lower_title = title.lower()
    return any(keyword.lower() in lower_title for keyword in keywords)


def _clean_text(value: str) -> str:
    value = unescape(value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _stable_document_id(source_name: str, key: str) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    safe_source = re.sub(r"[^a-zA-Z0-9_-]+", "-", source_name.lower()).strip("-")
    return f"{safe_source}-{digest}"
