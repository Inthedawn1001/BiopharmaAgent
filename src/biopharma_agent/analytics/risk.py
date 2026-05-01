"""Rule-based risk scoring for early warning signals."""

from __future__ import annotations

from dataclasses import dataclass


RISK_WEIGHTS = {
    "临床失败": 5,
    "终止": 4,
    "暂停": 4,
    "监管调查": 5,
    "诉讼": 3,
    "退市": 5,
    "亏损扩大": 3,
    "failed trial": 5,
    "terminated": 4,
    "clinical hold": 5,
    "investigation": 4,
    "litigation": 3,
    "delisting": 5,
}


@dataclass
class RuleBasedRiskScorer:
    """Score risk from explicit high-signal phrases."""

    weights: dict[str, int] | None = None

    def score(self, text: str) -> dict[str, object]:
        weights = self.weights or RISK_WEIGHTS
        normalized = text.lower()
        matched = [
            {"term": term, "weight": weight}
            for term, weight in weights.items()
            if term.lower() in normalized
        ]
        raw_score = sum(item["weight"] for item in matched)
        if raw_score >= 8:
            severity = "high"
        elif raw_score >= 4:
            severity = "medium"
        elif raw_score:
            severity = "low"
        else:
            severity = "none"
        return {"score": raw_score, "severity": severity, "matches": matched}

