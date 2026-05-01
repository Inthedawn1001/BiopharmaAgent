"""Cross-document intelligence brief generation."""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from biopharma_agent.analytics.topic import KeywordTopicAnalyzer
from biopharma_agent.storage.repository import document_quality


class IntelligenceBriefBuilder:
    """Build an operational intelligence brief from stored analysis records."""

    def __init__(self, topic_analyzer: KeywordTopicAnalyzer | None = None) -> None:
        self.topic_analyzer = topic_analyzer or KeywordTopicAnalyzer()

    def build(
        self,
        records: list[dict[str, Any]],
        *,
        generated_at: datetime | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        generated_at = generated_at or datetime.now(timezone.utc)
        selected = records[-max(1, limit) :]
        rows = [_brief_row(record) for record in selected]
        event_counts = Counter(row["event_type"] or "unknown" for row in rows)
        risk_counts = Counter(row["risk"] or "unknown" for row in rows)
        source_counts = Counter(row["source"] or "unknown" for row in rows)
        terms = self.topic_analyzer.top_terms(" ".join(row["text"] for row in rows), limit=12)
        key_developments = _key_developments(rows)
        risk_watchlist = [row for row in rows if row["risk"] in {"high", "medium"}][:8]
        summary = _executive_summary(
            rows=rows,
            event_counts=event_counts,
            risk_counts=risk_counts,
            terms=terms,
        )
        return {
            "generated_at": _isoformat(generated_at),
            "document_count": len(rows),
            "summary": summary,
            "event_counts": _counter_items(event_counts),
            "risk_counts": _counter_items(risk_counts),
            "source_counts": _counter_items(source_counts),
            "top_terms": [{"term": term, "count": count} for term, count in terms],
            "key_developments": key_developments,
            "risk_watchlist": risk_watchlist,
            "markdown": _render_markdown(
                generated_at=_isoformat(generated_at),
                document_count=len(rows),
                summary=summary,
                event_counts=event_counts,
                risk_counts=risk_counts,
                source_counts=source_counts,
                terms=terms,
                key_developments=key_developments,
                risk_watchlist=risk_watchlist,
            ),
        }


def write_intelligence_brief_artifacts(
    brief: dict[str, Any],
    *,
    markdown_path: Path | None = None,
    json_path: Path | None = None,
) -> dict[str, str]:
    """Persist a generated brief as Markdown and/or JSON artifacts."""

    outputs: dict[str, str] = {}
    if markdown_path is not None:
        markdown_path.parent.mkdir(parents=True, exist_ok=True)
        markdown_path.write_text(str(brief.get("markdown") or ""), encoding="utf-8")
        outputs["markdown"] = str(markdown_path)
    if json_path is not None:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(brief, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        outputs["json"] = str(json_path)
    return outputs


def _brief_row(record: dict[str, Any]) -> dict[str, Any]:
    document = record.get("document") if isinstance(record.get("document"), dict) else {}
    raw = document.get("raw") if isinstance(document.get("raw"), dict) else {}
    source = raw.get("source") if isinstance(raw.get("source"), dict) else {}
    insight = record.get("insight") if isinstance(record.get("insight"), dict) else {}
    events = insight.get("events") if isinstance(insight.get("events"), list) else []
    risks = insight.get("risk_signals") if isinstance(insight.get("risk_signals"), list) else []
    first_event = events[0] if events and isinstance(events[0], dict) else {}
    highest_risk = _highest_risk(risks)
    text = " ".join(
        value
        for value in [
            str(raw.get("title") or ""),
            str(insight.get("summary") or ""),
            str(document.get("text") or raw.get("raw_text") or ""),
        ]
        if value
    )
    quality = document_quality(record)
    return {
        "id": str(raw.get("document_id") or document.get("checksum") or ""),
        "title": str(raw.get("title") or insight.get("summary") or "Untitled"),
        "source": str(source.get("name") or ""),
        "url": str(raw.get("url") or ""),
        "created_at": str(record.get("created_at") or ""),
        "summary": str(insight.get("summary") or ""),
        "event_type": str(first_event.get("event_type") or "unknown"),
        "event_title": str(first_event.get("title") or ""),
        "risk": highest_risk,
        "needs_human_review": bool(insight.get("needs_human_review")),
        "body_quality": quality["label"],
        "text_length": quality["text_length"],
        "text": text,
    }


def _key_developments(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(rows, key=_development_sort_key)
    return [
        {key: row[key] for key in ["id", "title", "source", "event_type", "risk", "summary", "url", "created_at"]}
        for row in ranked[:8]
    ]


def _development_sort_key(row: dict[str, Any]) -> tuple[int, str]:
    risk_rank = {"high": 0, "medium": 1, "low": 2, "unknown": 3, "": 4}
    return (risk_rank.get(str(row.get("risk") or ""), 4), str(row.get("created_at") or ""))


def _executive_summary(
    *,
    rows: list[dict[str, Any]],
    event_counts: Counter[str],
    risk_counts: Counter[str],
    terms: list[tuple[str, int]],
) -> str:
    if not rows:
        return "No analyzed documents are available for this brief."
    top_event = event_counts.most_common(1)[0][0]
    top_risk = risk_counts.most_common(1)[0][0]
    term_text = ", ".join(term for term, _ in terms[:3]) or "no dominant terms"
    return (
        f"{len(rows)} analyzed documents indicate {top_event} as the leading event theme. "
        f"The dominant risk level is {top_risk}. Key terms are {term_text}."
    )


def _render_markdown(
    *,
    generated_at: str,
    document_count: int,
    summary: str,
    event_counts: Counter[str],
    risk_counts: Counter[str],
    source_counts: Counter[str],
    terms: list[tuple[str, int]],
    key_developments: list[dict[str, Any]],
    risk_watchlist: list[dict[str, Any]],
) -> str:
    lines = [
        "# Biopharma Intelligence Brief",
        "",
        f"- Generated: {generated_at}",
        f"- Documents: {document_count}",
        "",
        "## Executive Summary",
        "",
        summary,
        "",
        "## Signals",
        "",
        f"- Event mix: {_counter_phrase(event_counts)}",
        f"- Risk mix: {_counter_phrase(risk_counts)}",
        f"- Top sources: {_counter_phrase(source_counts, limit=4)}",
        f"- Top terms: {', '.join(f'{term} ({count})' for term, count in terms[:8]) or '-'}",
        "",
        "## Key Developments",
        "",
    ]
    if key_developments:
        lines.extend(["| Risk | Event | Source | Title |", "| --- | --- | --- | --- |"])
        for row in key_developments:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md(row.get("risk")),
                        _md(row.get("event_type")),
                        _md(row.get("source")),
                        _md(row.get("title")),
                    ]
                )
                + " |"
            )
    else:
        lines.append("No key developments are available.")

    lines.extend(["", "## Risk Watchlist", ""])
    if risk_watchlist:
        lines.extend(["| Risk | Source | Development |", "| --- | --- | --- |"])
        for row in risk_watchlist:
            lines.append(
                "| "
                + " | ".join(
                    [_md(row.get("risk")), _md(row.get("source")), _md(row.get("summary") or row.get("title"))]
                )
                + " |"
            )
    else:
        lines.append("No medium or high risk items found.")
    lines.append("")
    return "\n".join(lines)


def _highest_risk(risks: list[Any]) -> str:
    order = {"high": 3, "medium": 2, "low": 1, "unknown": 0}
    best = "unknown"
    best_score = -1
    for risk in risks:
        if not isinstance(risk, dict):
            continue
        severity = str(risk.get("severity", "")).lower()
        score = order.get(severity, -1)
        if score > best_score:
            best = severity or "unknown"
            best_score = score
    return best


def _counter_items(counter: Counter[str]) -> list[dict[str, Any]]:
    return [{"name": name, "count": count} for name, count in counter.most_common()]


def _counter_phrase(counter: Counter[str], limit: int = 5) -> str:
    return ", ".join(f"{name} ({count})" for name, count in counter.most_common(limit)) or "-"


def _md(value: Any) -> str:
    return str(value or "-").replace("\n", " ").replace("|", "\\|").strip() or "-"


def _isoformat(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()
