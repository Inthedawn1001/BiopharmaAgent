"""Combined deterministic analytics report."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from biopharma_agent.analytics.risk import RuleBasedRiskScorer
from biopharma_agent.analytics.sentiment import KeywordSentimentAnalyzer
from biopharma_agent.analytics.topic import KeywordTopicAnalyzer


@dataclass
class DeterministicTextAnalytics:
    topic_analyzer: KeywordTopicAnalyzer = field(default_factory=KeywordTopicAnalyzer)
    sentiment_analyzer: KeywordSentimentAnalyzer = field(default_factory=KeywordSentimentAnalyzer)
    risk_scorer: RuleBasedRiskScorer = field(default_factory=RuleBasedRiskScorer)

    def analyze(self, text: str) -> dict[str, Any]:
        return {
            "top_terms": self.topic_analyzer.top_terms(text),
            "sentiment": self.sentiment_analyzer.analyze(text),
            "risk": self.risk_scorer.score(text),
        }
