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
    "into",
    "over",
    "under",
    "between",
    "after",
    "before",
    "while",
    "during",
    "this",
    "that",
    "these",
    "those",
    "about",
    "the",
    "for",
    "and",
    "but",
    "or",
    "not",
    "are",
    "was",
    "were",
    "has",
    "have",
    "had",
    "will",
    "would",
    "could",
    "should",
    "may",
    "can",
    "its",
    "their",
    "our",
    "his",
    "her",
    "in",
    "of",
    "to",
    "on",
    "at",
    "by",
    "as",
    "is",
    "be",
    "a",
    "an",
    "company",
    "announced",
    "completed",
    "related",
    "also",
}

DOMAIN_TERMS = {
    "ipo",
    "m&a",
    "pd-1",
    "pd-l1",
    "car-t",
    "financing",
    "merger",
    "acquisition",
    "listing",
    "clinical",
    "clinical failure",
    "approval",
    "indication",
    "target",
    "drug",
    "innovative drug",
    "regulatory",
    "reimbursement",
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

        for token in re.findall(r"[A-Za-z][A-Za-z0-9-]+", stripped):
            token = token.lower()
            if len(token) >= self.min_token_length and token not in stopwords:
                counter[token] += 1
        return sorted(counter.items(), key=lambda item: (-item[1], item[0]))[:limit]
