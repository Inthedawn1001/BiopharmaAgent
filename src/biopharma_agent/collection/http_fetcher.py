"""Lightweight HTTP fetcher for the collection MVP."""

from __future__ import annotations

import socket
import urllib.error
import urllib.request
import urllib.robotparser
from dataclasses import dataclass
from email.message import Message
from typing import Protocol
from urllib.parse import urlparse

from biopharma_agent.contracts import RawDocument, SourceRef, utc_now


class HTTPTransport(Protocol):
    def get(self, url: str, headers: dict[str, str], timeout: float) -> tuple[int, Message, bytes]:
        """Fetch a URL and return status code, headers, and body bytes."""


class UrllibHTTPTransport:
    """Dependency-free HTTP transport."""

    def get(self, url: str, headers: dict[str, str], timeout: float) -> tuple[int, Message, bytes]:
        request = urllib.request.Request(url=url, headers=headers, method="GET")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.headers, response.read()


@dataclass(frozen=True)
class HTTPFetchResult:
    raw_document: RawDocument
    status_code: int
    content_type: str


@dataclass
class HTTPSourceFetcher:
    """Fetch a web page into the internal RawDocument contract."""

    transport: HTTPTransport = UrllibHTTPTransport()
    user_agent: str = "biopharma-agent/0.1"
    timeout_seconds: float = 30.0
    respect_robots_txt: bool = True

    def fetch(
        self,
        url: str,
        source: SourceRef | None = None,
        document_id: str | None = None,
    ) -> HTTPFetchResult:
        source = source or SourceRef(name=urlparse(url).netloc or "unknown", kind="web", url=url)
        if self.respect_robots_txt and not self._allowed_by_robots(url):
            raise PermissionError(f"robots.txt disallows fetching {url}")

        try:
            status, headers, body = self.transport.get(
                url,
                headers={"User-Agent": self.user_agent},
                timeout=self.timeout_seconds,
            )
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"HTTP {exc.code} while fetching {url}") from exc
        except (urllib.error.URLError, socket.timeout) as exc:
            raise RuntimeError(f"Failed to fetch {url}: {exc}") from exc

        content_type = headers.get("Content-Type", "")
        charset = headers.get_content_charset() or "utf-8"
        text = body.decode(charset, errors="replace")
        raw = RawDocument(
            source=source,
            document_id=document_id or _document_id_from_url(url),
            collected_at=utc_now(),
            url=url,
            raw_text=text,
            metadata={
                "content_type": content_type,
                "status_code": status,
                "headers": dict(headers.items()),
            },
        )
        return HTTPFetchResult(raw_document=raw, status_code=status, content_type=content_type)

    def _allowed_by_robots(self, url: str) -> bool:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return True
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(robots_url)
        try:
            parser.read()
        except Exception:
            return True
        return parser.can_fetch(self.user_agent, url)


def _document_id_from_url(url: str) -> str:
    parsed = urlparse(url)
    path = parsed.path.strip("/").replace("/", "-") or "index"
    host = parsed.netloc.replace(":", "-")
    timestamp = utc_now().strftime("%Y%m%d%H%M%S")
    return f"{host}-{path}-{timestamp}"
