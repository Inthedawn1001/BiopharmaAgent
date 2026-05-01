"""Utilities for robustly reading model JSON."""

from __future__ import annotations

import json
from typing import Any

from biopharma_agent.llm.errors import LLMResponseError


def parse_json_object(text: str) -> dict[str, Any]:
    """Parse JSON even when a model wraps it in markdown fences or extra text."""

    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise LLMResponseError(f"Model response did not contain a JSON object: {text[:500]}")
        try:
            parsed = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise LLMResponseError(f"Could not parse model JSON: {text[:500]}") from exc

    if not isinstance(parsed, dict):
        raise LLMResponseError(f"Expected JSON object, got {type(parsed).__name__}")
    return parsed

