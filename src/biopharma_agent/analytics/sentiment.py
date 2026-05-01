"""Simple keyword sentiment analysis."""

from __future__ import annotations

import re
from dataclasses import dataclass


POSITIVE_TERMS = {
    "获批",
    "突破",
    "增长",
    "盈利",
    "融资",
    "合作",
    "positive",
    "growth",
    "approval",
    "profit",
    "partnership",
    "financing",
}

NEGATIVE_TERMS = {
    "失败",
    "终止",
    "下滑",
    "亏损",
    "调查",
    "诉讼",
    "风险",
    "failed",
    "terminate",
    "decline",
    "loss",
    "investigation",
    "litigation",
    "risk",
}


@dataclass
class KeywordSentimentAnalyzer:
    """Return a coarse sentiment score from keyword matches."""

    positive_terms: set[str] | None = None
    negative_terms: set[str] | None = None

    def analyze(self, text: str) -> dict[str, float | str | int]:
        positive_terms = self.positive_terms or POSITIVE_TERMS
        negative_terms = self.negative_terms or NEGATIVE_TERMS
        normalized = text.lower()
        positive = sum(_count_term(normalized, term.lower()) for term in positive_terms)
        negative = sum(_count_term(normalized, term.lower()) for term in negative_terms)
        score = (positive - negative) / max(1, positive + negative)
        label = "neutral"
        if score >= 0.25:
            label = "positive"
        elif score <= -0.25:
            label = "negative"
        return {
            "label": label,
            "score": round(score, 4),
            "positive_hits": positive,
            "negative_hits": negative,
        }


def _count_term(text: str, term: str) -> int:
    if re.search(r"[\u4e00-\u9fff]", term):
        return text.count(term)
    return len(re.findall(rf"\b{re.escape(term)}\b", text))

