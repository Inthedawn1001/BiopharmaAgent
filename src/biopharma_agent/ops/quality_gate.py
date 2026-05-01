"""Production-readiness quality gates for stored intelligence artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from biopharma_agent.storage.repository import document_quality


def run_quality_gate(
    *,
    analysis_path: Path,
    brief_markdown_path: Path | None = None,
    source_state_path: Path | None = None,
    min_records: int = 1,
    min_summary_ratio: float = 0.8,
    min_event_ratio: float = 0.6,
    min_risk_ratio: float = 0.6,
    min_usable_body_ratio: float = 0.5,
    max_failed_sources: int = 0,
    require_brief: bool = False,
    require_source_state: bool = False,
) -> dict[str, Any]:
    """Validate that recent local outputs are complete enough for operator use."""

    records = _load_jsonl(analysis_path) if analysis_path.exists() else []
    checks: list[dict[str, Any]] = []
    checks.append(_minimum_check("analysis_records", len(records), min_records))
    checks.append(_ratio_check("summary_coverage", _summary_ratio(records), min_summary_ratio))
    checks.append(_ratio_check("event_coverage", _event_ratio(records), min_event_ratio))
    checks.append(_ratio_check("risk_coverage", _risk_ratio(records), min_risk_ratio))
    checks.append(_ratio_check("usable_body_coverage", _usable_body_ratio(records), min_usable_body_ratio))

    if brief_markdown_path is not None:
        checks.extend(_brief_checks(brief_markdown_path, required=require_brief))
    elif require_brief:
        checks.append(_check("brief_present", "fail", "No brief Markdown path was supplied."))

    if source_state_path is not None:
        checks.extend(
            _source_state_checks(
                source_state_path,
                max_failed_sources=max_failed_sources,
                required=require_source_state,
            )
        )
    elif require_source_state:
        checks.append(_check("source_state_present", "fail", "No source-state path was supplied."))

    status = "pass" if all(item["status"] == "pass" for item in checks) else "fail"
    return {
        "status": status,
        "analysis_path": str(analysis_path),
        "brief_markdown_path": str(brief_markdown_path) if brief_markdown_path else "",
        "source_state_path": str(source_state_path) if source_state_path else "",
        "checks": checks,
        "summary": {
            "passed": sum(1 for item in checks if item["status"] == "pass"),
            "failed": sum(1 for item in checks if item["status"] == "fail"),
            "total": len(checks),
        },
    }


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        decoded = json.loads(line)
        if isinstance(decoded, dict):
            rows.append(decoded)
    return rows


def _summary_ratio(records: list[dict[str, Any]]) -> float:
    return _coverage_ratio(records, lambda record: bool(_insight(record).get("summary")))


def _event_ratio(records: list[dict[str, Any]]) -> float:
    return _coverage_ratio(records, lambda record: bool(_insight(record).get("events")))


def _risk_ratio(records: list[dict[str, Any]]) -> float:
    return _coverage_ratio(records, lambda record: bool(_insight(record).get("risk_signals")))


def _usable_body_ratio(records: list[dict[str, Any]]) -> float:
    return _coverage_ratio(
        records,
        lambda record: document_quality(record).get("label") in {"strong", "usable", "short"},
    )


def _coverage_ratio(records: list[dict[str, Any]], predicate) -> float:
    if not records:
        return 0.0
    return round(sum(1 for record in records if predicate(record)) / len(records), 4)


def _insight(record: dict[str, Any]) -> dict[str, Any]:
    insight = record.get("insight")
    return insight if isinstance(insight, dict) else {}


def _brief_checks(path: Path, *, required: bool) -> list[dict[str, Any]]:
    if not path.exists():
        if required:
            return [_check("brief_present", "fail", f"Brief Markdown not found at {path}.")]
        return [_check("brief_present", "pass", f"Optional brief Markdown not found at {path}.")]
    markdown = path.read_text(encoding="utf-8")
    required_sections = ["Executive Summary", "Signals", "Key Developments", "Risk Watchlist"]
    missing = [section for section in required_sections if section not in markdown]
    return [
        _check("brief_present", "pass", "Brief Markdown artifact exists."),
        _check(
            "brief_sections",
            "pass" if not missing else "fail",
            "Brief contains required sections." if not missing else f"Missing sections: {', '.join(missing)}.",
        ),
    ]


def _source_state_checks(
    path: Path,
    *,
    max_failed_sources: int,
    required: bool,
) -> list[dict[str, Any]]:
    if not path.exists():
        if required:
            return [_check("source_state_present", "fail", f"Source state not found at {path}.")]
        return [_check("source_state_present", "pass", f"Optional source state not found at {path}.")]
    decoded = json.loads(path.read_text(encoding="utf-8") or "{}")
    sources = decoded.get("sources", {}) if isinstance(decoded, dict) else {}
    rows = [item for item in sources.values() if isinstance(item, dict)] if isinstance(sources, dict) else []
    failed = sum(1 for item in rows if item.get("last_status") == "failed")
    return [
        _check("source_state_present", "pass", "Source-state artifact exists."),
        _maximum_check("failed_sources", failed, max_failed_sources),
    ]


def _minimum_check(name: str, observed: int | float, minimum: int | float) -> dict[str, Any]:
    return _check(
        name,
        "pass" if observed >= minimum else "fail",
        f"Observed {observed}; minimum {minimum}.",
        observed=observed,
        threshold=minimum,
    )


def _maximum_check(name: str, observed: int | float, maximum: int | float) -> dict[str, Any]:
    return _check(
        name,
        "pass" if observed <= maximum else "fail",
        f"Observed {observed}; maximum {maximum}.",
        observed=observed,
        threshold=maximum,
    )


def _ratio_check(name: str, observed: float, minimum: float) -> dict[str, Any]:
    return _minimum_check(name, observed, minimum)


def _check(
    name: str,
    status: str,
    message: str,
    *,
    observed: int | float | str = "",
    threshold: int | float | str = "",
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "observed": observed,
        "threshold": threshold,
        "message": message,
    }
