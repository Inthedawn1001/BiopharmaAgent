"""ASX announcement collection adapters."""

from __future__ import annotations

import hashlib
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from email.message import Message
from html import unescape
from html.parser import HTMLParser
from typing import Protocol

from biopharma_agent.contracts import RawDocument, SourceRef, utc_now


class ASXTransport(Protocol):
    def get(self, url: str, headers: dict[str, str], timeout: float) -> tuple[int, Message, bytes]:
        """Fetch an ASX URL."""


class UrllibASXTransport:
    def get(self, url: str, headers: dict[str, str], timeout: float) -> tuple[int, Message, bytes]:
        request = urllib.request.Request(url=url, headers=headers, method="GET")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.headers, response.read()


@dataclass(frozen=True)
class ASXAnnouncement:
    ticker: str
    title: str
    url: str
    released_at: str = ""
    pages: str = ""
    file_size: str = ""


@dataclass(frozen=True)
class ASXFetchResult:
    source: SourceRef
    status_code: int
    announcements: list[ASXAnnouncement]
    searched_tickers: list[str]

    def to_raw_documents(self, limit: int | None = None) -> list[RawDocument]:
        selected = self.announcements[:limit] if limit is not None else self.announcements
        documents: list[RawDocument] = []
        for item in selected:
            text = "\n\n".join(part for part in [item.title, item.ticker, item.released_at, item.url] if part)
            documents.append(
                RawDocument(
                    source=self.source,
                    document_id=_stable_document_id(self.source.name, f"{item.ticker}:{item.url}"),
                    collected_at=utc_now(),
                    url=item.url,
                    title=item.title,
                    raw_text=text,
                    metadata={
                        "content_type": "asx_announcement",
                        "ticker": item.ticker,
                        "released_at": item.released_at,
                        "pages": item.pages,
                        "file_size": item.file_size,
                    },
                )
            )
        return documents


@dataclass
class ASXAnnouncementsFetcher:
    """Fetch ASX announcement search pages for a configured ticker watchlist."""

    transport: ASXTransport = UrllibASXTransport()
    user_agent: str = "biopharma-agent/0.1"
    timeout_seconds: float = 30.0

    def fetch(self, source: SourceRef) -> ASXFetchResult:
        tickers = _string_list(source.metadata.get("watchlist")) or ["CSL", "COH", "RMD"]
        period = str(source.metadata.get("period", "W"))
        announcements: list[ASXAnnouncement] = []
        status_code = 0
        for ticker in tickers:
            url = _announcement_search_url(ticker, period)
            try:
                status, headers, body = self.transport.get(
                    url,
                    headers={"User-Agent": self.user_agent},
                    timeout=self.timeout_seconds,
                )
            except urllib.error.HTTPError as exc:
                raise RuntimeError(f"HTTP {exc.code} while fetching ASX announcements for {ticker}") from exc
            except (urllib.error.URLError, socket.timeout) as exc:
                raise RuntimeError(f"Failed to fetch ASX announcements for {ticker}: {exc}") from exc
            status_code = status
            charset = headers.get_content_charset() or "utf-8"
            html = body.decode(charset, errors="replace")
            announcements.extend(parse_asx_announcements(html, ticker=ticker))
        return ASXFetchResult(
            source=source,
            status_code=status_code or 200,
            announcements=_dedupe_announcements(announcements),
            searched_tickers=tickers,
        )


def parse_asx_announcements(html: str, ticker: str) -> list[ASXAnnouncement]:
    parser = _ASXLinkParser()
    parser.feed(html)
    announcements: list[ASXAnnouncement] = []
    for link_text, href in parser.links:
        absolute_url = urllib.parse.urljoin("https://www.asx.com.au", href)
        if not _looks_like_announcement_url(absolute_url):
            continue
        title = _clean_title(link_text)
        if not title:
            continue
        context = parser.context_for(href)
        announcements.append(
            ASXAnnouncement(
                ticker=ticker.upper(),
                title=title,
                url=absolute_url,
                released_at=_first_match(context, r"\b\d{1,2}/\d{1,2}/\d{4}\b|\b\d{1,2}:\d{2}\s*(?:AM|PM)?\b"),
                pages=_first_match(context, r"\b\d+\s+pages?\b"),
                file_size=_first_match(context, r"\b\d+(?:\.\d+)?\s*(?:KB|MB)\b"),
            )
        )
    return announcements


class _ASXLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str]] = []
        self._href: str | None = None
        self._parts: list[str] = []
        self._all_text_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attrs_dict = {key.lower(): value or "" for key, value in attrs}
        href = attrs_dict.get("href", "")
        if href:
            self._href = href
            self._parts = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self._href:
            text = _clean_text(" ".join(self._parts))
            if text:
                self.links.append((text, self._href))
            self._href = None
            self._parts = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return
        self._all_text_parts.append(text)
        if self._href:
            self._parts.append(text)

    def context_for(self, href: str) -> str:
        del href
        return _clean_text(" ".join(self._all_text_parts))


def _announcement_search_url(ticker: str, period: str) -> str:
    params = urllib.parse.urlencode(
        {
            "by": "asxCode",
            "asxCode": ticker.upper()[:3],
            "timeframe": "D",
            "period": period,
        }
    )
    return f"https://www.asx.com.au/asx/v2/statistics/announcements.do?{params}"


def _looks_like_announcement_url(url: str) -> bool:
    lower = url.lower()
    return "/asxpdf/" in lower or "displayannouncement" in lower or "announcements" in lower and ".pdf" in lower


def _clean_title(value: str) -> str:
    return re.sub(r"^(open|view|download)\s+", "", _clean_text(value), flags=re.I)


def _clean_text(value: str) -> str:
    value = unescape(value or "")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _first_match(value: str, pattern: str) -> str:
    match = re.search(pattern, value, flags=re.I)
    return match.group(0) if match else ""


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _dedupe_announcements(items: list[ASXAnnouncement]) -> list[ASXAnnouncement]:
    seen: set[str] = set()
    deduped: list[ASXAnnouncement] = []
    for item in items:
        key = item.url
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _stable_document_id(source_name: str, key: str) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    safe_source = re.sub(r"[^a-zA-Z0-9_-]+", "-", source_name.lower()).strip("-")
    return f"{safe_source}-{digest}"
