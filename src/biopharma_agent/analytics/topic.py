"""Lightweight keyword topic analysis for the MVP."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass


DEFAULT_STOPWORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "this",
    "that",
    "into",
    "about",
    "公司",
    "宣布",
    "进行",
    "完成",
    "相关",
    "以及",
    "一个",
}

DOMAIN_TERMS = {
    "ipo",
    "m&a",
    "pd-1",
    "pd-l1",
    "car-t",
    "融资",
    "并购",
    "上市",
    "临床",
    "临床失败",
    "获批",
    "适应症",
    "靶点",
    "药物",
    "创新药",
    "监管",
    "医保",
}


@dataclass
class KeywordTopicAnalyzer:
    """Extract high-frequency terms as a deterministic topic hint."""

    stopwords: set[str] | None = None
    domain_terms: set[str] | None = None
    min_token_length: int = 2

    def top_terms(self, text: str, limit: int = 10) -> list[tuple[str, int]]:
        stopwords = self.stopwords or DEFAULT_STOPWORDS
        domain_terms = self.domain_terms or DOMAIN_TERMS
        lowered = text.lower()
        counter: Counter[str] = Counter()
        for term in domain_terms:
            count = lowered.count(term.lower())
            if count:
                counter[term.lower()] += count

        stripped = lowered
        for term in sorted(domain_terms, key=len, reverse=True):
            stripped = stripped.replace(term.lower(), " ")

        for token in re.findall(r"[A-Za-z][A-Za-z0-9-]+|[\u4e00-\u9fff]{2,}", stripped):
            token = token.lower()
            if len(token) >= self.min_token_length and token not in stopwords:
                counter[token] += 1
        return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit]
