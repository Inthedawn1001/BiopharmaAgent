"""JSON schemas for LLM structured extraction."""

from __future__ import annotations

from typing import Any


DOCUMENT_INSIGHT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "language": {"type": "string"},
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "name": {"type": "string"},
                    "type": {
                        "type": "string",
                        "enum": [
                            "company",
                            "person",
                            "drug",
                            "target",
                            "indication",
                            "trial",
                            "regulator",
                            "investor",
                            "exchange",
                            "policy",
                            "other",
                        ],
                    },
                    "normalized_name": {"type": "string"},
                    "confidence": {"type": "number"},
                    "evidence": {"type": "string"},
                },
                "required": ["name", "type", "normalized_name", "confidence", "evidence"],
            },
        },
        "events": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "event_type": {
                        "type": "string",
                        "enum": [
                            "financing",
                            "ipo",
                            "ma",
                            "clinical_trial",
                            "approval",
                            "partnership",
                            "earnings",
                            "policy",
                            "litigation",
                            "risk",
                            "other",
                        ],
                    },
                    "title": {"type": "string"},
                    "date": {"type": "string"},
                    "companies": {"type": "array", "items": {"type": "string"}},
                    "amount": {"type": "string"},
                    "stage": {"type": "string"},
                    "confidence": {"type": "number"},
                    "evidence": {"type": "string"},
                },
                "required": [
                    "event_type",
                    "title",
                    "date",
                    "companies",
                    "amount",
                    "stage",
                    "confidence",
                    "evidence",
                ],
            },
        },
        "relations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "subject": {"type": "string"},
                    "predicate": {"type": "string"},
                    "object": {"type": "string"},
                    "confidence": {"type": "number"},
                    "evidence": {"type": "string"},
                },
                "required": ["subject", "predicate", "object", "confidence", "evidence"],
            },
        },
        "risk_signals": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "risk_type": {"type": "string"},
                    "severity": {"type": "string", "enum": ["low", "medium", "high", "unknown"]},
                    "description": {"type": "string"},
                    "evidence": {"type": "string"},
                },
                "required": ["risk_type", "severity", "description", "evidence"],
            },
        },
        "market_implications": {"type": "array", "items": {"type": "string"}},
        "needs_human_review": {"type": "boolean"},
    },
    "required": [
        "summary",
        "language",
        "entities",
        "events",
        "relations",
        "risk_signals",
        "market_implications",
        "needs_human_review",
    ],
}

