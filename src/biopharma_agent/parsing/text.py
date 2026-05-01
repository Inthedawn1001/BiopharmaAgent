"""Dependency-free document text parsers for the MVP."""

from __future__ import annotations

import hashlib
import html
import re
from html.parser import HTMLParser
from typing import Protocol

from biopharma_agent.contracts import ParsedDocument, RawDocument


class DocumentParser(Protocol):
    def parse(self, raw: RawDocument) -> ParsedDocument:
        """Parse a raw document into normalized text."""


class PlainTextParser:
    """Normalize plain text documents."""

    def parse(self, raw: RawDocument) -> ParsedDocument:
        text = normalize_text(raw.raw_text or "")
        return ParsedDocument(
            raw=raw,
            text=text,
            checksum=checksum_text(text),
            language=detect_language(text),
            published_at=raw.metadata.get("published_at"),
            authors=list(raw.metadata.get("authors", [])),
            metadata={"parser": "plain_text"},
        )


class HTMLTextParser:
    """Extract visible text from simple HTML without external dependencies."""

    def parse(self, raw: RawDocument) -> ParsedDocument:
        extracted = extract_main_text(raw.raw_text or "")
        return ParsedDocument(
            raw=raw,
            text=extracted.text,
            checksum=checksum_text(extracted.text),
            language=detect_language(extracted.text),
            published_at=raw.metadata.get("published_at"),
            authors=list(raw.metadata.get("authors", [])),
            metadata={
                "parser": "html_text",
                "extraction_method": extracted.method,
                "extraction_score": extracted.score,
            },
        )


def parse_raw_document(raw: RawDocument) -> ParsedDocument:
    content_type = str(raw.metadata.get("content_type", "")).lower()
    body = raw.raw_text or ""
    if "html" in content_type or looks_like_html(body):
        return HTMLTextParser().parse(raw)
    return PlainTextParser().parse(raw)


def normalize_text(text: str) -> str:
    text = text.replace("\u3000", " ")
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def checksum_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def detect_language(text: str) -> str | None:
    if not text:
        return None
    cjk_count = sum(1 for char in text if "\u4e00" <= char <= "\u9fff")
    alpha_count = sum(1 for char in text if char.isascii() and char.isalpha())
    if cjk_count >= max(3, alpha_count // 4):
        return "zh"
    if alpha_count:
        return "en"
    return None


def looks_like_html(text: str) -> bool:
    return bool(re.search(r"<(html|body|article|p|div|span|section|head)\b", text, re.I))


class ExtractedText:
    def __init__(self, text: str, method: str, score: float) -> None:
        self.text = text
        self.method = method
        self.score = score


def extract_main_text(html_text: str) -> ExtractedText:
    extractor = _VisibleTextExtractor()
    extractor.feed(html_text)
    preferred = extractor.preferred_text()
    if preferred:
        text = normalize_text(html.unescape(preferred))
        return ExtractedText(text=text, method="semantic_container", score=float(len(text)))

    best_block = extractor.best_block()
    if best_block:
        text = normalize_text(html.unescape(best_block[0]))
        return ExtractedText(text=text, method="density_block", score=best_block[1])

    text = normalize_text(html.unescape(" ".join(extractor.parts)))
    return ExtractedText(text=text, method="visible_text", score=float(len(text)))


class _VisibleTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._container_stack: list[dict[str, object]] = []
        self._blocks: list[tuple[str, str]] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        lower_tag = tag.lower()
        if lower_tag in {"script", "style", "noscript", "svg", "nav", "footer", "header"}:
            self._skip_depth += 1
            return
        if lower_tag in {"article", "main", "section", "div", "p"}:
            attrs_dict = {key.lower(): value or "" for key, value in attrs}
            self._container_stack.append(
                {
                    "tag": lower_tag,
                    "attrs": attrs_dict,
                    "parts": [],
                }
            )

    def handle_endtag(self, tag: str) -> None:
        lower_tag = tag.lower()
        if lower_tag in {"script", "style", "noscript", "svg", "nav", "footer", "header"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if lower_tag in {"article", "main", "section", "div", "p"} and self._container_stack:
            container = self._container_stack.pop()
            if container.get("tag") == lower_tag:
                text = normalize_text(" ".join(container.get("parts", [])))
                if text:
                    self._blocks.append((lower_tag, text))
                    if self._container_stack:
                        self._container_stack[-1]["parts"].append(text)  # type: ignore[index, union-attr]

    def handle_data(self, data: str) -> None:
        if not self._skip_depth and data.strip():
            text = data.strip()
            self.parts.append(text)
            for container in self._container_stack:
                container["parts"].append(text)  # type: ignore[index, union-attr]

    def preferred_text(self) -> str:
        semantic_blocks = [
            text
            for tag, text in self._blocks
            if tag in {"article", "main"} and len(text) >= 80
        ]
        if semantic_blocks:
            return max(semantic_blocks, key=len)
        return ""

    def best_block(self) -> tuple[str, float] | None:
        best: tuple[str, float] | None = None
        for tag, text in self._blocks:
            if tag not in {"section", "div", "p"}:
                continue
            word_count = len(re.findall(r"\w+", text))
            linkish_penalty = 0.65 if tag == "p" else 1.0
            score = (len(text) + word_count * 5) * linkish_penalty
            if len(text) < 80:
                continue
            if best is None or score > best[1]:
                best = (text, score)
        return best
