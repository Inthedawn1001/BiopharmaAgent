"""Operator report builders for source health and scheduled runs."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def build_source_health_report(
    source_state: dict[str, Any],
    runs: dict[str, Any],
    *,
    generated_at: datetime | None = None,
    max_alerts: int = 8,
    max_sources: int = 10,
) -> dict[str, Any]:
    """Return a Markdown report and structured summary for source operations."""

    generated_at = generated_at or datetime.now(timezone.utc)
    state_summary = source_state.get("summary", {}) if isinstance(source_state, dict) else {}
    run_summary = runs.get("summary", {}) if isinstance(runs, dict) else {}
    alerts = _dict_list(source_state.get("alerts", []))
    items = _dict_list(source_state.get("items", []))
    run_items = _dict_list(runs.get("items", []))
    alert_counts = _alert_counts(state_summary, alerts)
    report_summary = {
        "generated_at": _stringify_datetime(generated_at),
        "source_count": int(source_state.get("count", len(items)) or 0),
        "health_ratio": float(state_summary.get("health_ratio", 0) or 0),
        "healthy_sources": int(state_summary.get("success", 0) or 0),
        "failed_sources": int(state_summary.get("failed", 0) or 0),
        "never_run_sources": int(state_summary.get("never_run", 0) or 0),
        "alert_counts": alert_counts,
        "latest_run_status": str(run_summary.get("latest_status") or ""),
        "latest_run_completed_at": str(run_summary.get("latest_completed_at") or ""),
        "run_success": int(run_summary.get("success", 0) or 0),
        "run_failed": int(run_summary.get("failed", 0) or 0),
        "selected": int(run_summary.get("selected", 0) or 0),
        "analyzed": int(run_summary.get("analyzed", 0) or 0),
        "skipped_seen": int(run_summary.get("skipped_seen", 0) or 0),
    }
    markdown = _render_markdown(
        source_state=source_state,
        runs=runs,
        summary=report_summary,
        alerts=alerts[: max(0, max_alerts)],
        sources=_prioritized_sources(items)[: max(0, max_sources)],
        run_items=run_items[:5],
    )
    return {
        "generated_at": report_summary["generated_at"],
        "summary": report_summary,
        "markdown": markdown,
    }


def _render_markdown(
    *,
    source_state: dict[str, Any],
    runs: dict[str, Any],
    summary: dict[str, Any],
    alerts: list[dict[str, Any]],
    sources: list[dict[str, Any]],
    run_items: list[dict[str, Any]],
) -> str:
    lines = [
        "# Biopharma Agent Source Health Report",
        "",
        f"- Generated: {summary['generated_at']}",
        f"- Source state backend: {source_state.get('backend', '-')}",
        f"- Source state path: {_display_path(source_state.get('path'))}",
        f"- Run log path: {_display_path(runs.get('path'))}",
        "",
        "## Executive Summary",
        "",
        f"- Health: {round(summary['health_ratio'] * 100)}%",
        (
            f"- Sources: {summary['source_count']} total, "
            f"{summary['healthy_sources']} healthy, "
            f"{summary['failed_sources']} failed, "
            f"{summary['never_run_sources']} never run"
        ),
        (
            f"- Alerts: {summary['alert_counts']['critical']} critical, "
            f"{summary['alert_counts']['warning']} warning, "
            f"{summary['alert_counts']['info']} info"
        ),
        (
            f"- Recent runs: {summary['run_success']} success, "
            f"{summary['run_failed']} failed, latest {summary['latest_run_status'] or '-'} "
            f"at {summary['latest_run_completed_at'] or '-'}"
        ),
        (
            f"- Collection totals: {summary['selected']} selected, "
            f"{summary['analyzed']} analyzed, {summary['skipped_seen']} skipped as seen"
        ),
        "",
        "## Priority Alerts",
        "",
    ]
    if alerts:
        lines.extend(
            [
                "| Level | Source | Category | Consecutive | Action |",
                "| --- | --- | --- | ---: | --- |",
            ]
        )
        for alert in alerts:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md(alert.get("level")),
                        _md(alert.get("source")),
                        _md(alert.get("category")),
                        str(int(alert.get("consecutive_failures", 0) or 0)),
                        _md(alert.get("action") or alert.get("message")),
                    ]
                )
                + " |"
            )
    else:
        lines.append("No active source alerts.")

    lines.extend(["", "## Source Snapshot", ""])
    if sources:
        lines.extend(
            [
                "| Source | Status | Diagnosis | Seen | Updated |",
                "| --- | --- | --- | ---: | --- |",
            ]
        )
        for source in sources:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md(source.get("source")),
                        _md(source.get("last_status")),
                        _md(source.get("failure_type")),
                        str(int(source.get("seen_count", 0) or 0)),
                        _md(source.get("last_completed_at") or source.get("updated_at")),
                    ]
                )
                + " |"
            )
    else:
        lines.append("No source records are available.")

    lines.extend(["", "## Recent Runs", ""])
    if run_items:
        lines.extend(
            [
                "| Run | Status | Sources | Result | Completed |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for run in run_items:
            lines.append(
                "| "
                + " | ".join(
                    [
                        _md(run.get("run_id") or run.get("job_name")),
                        _md(run.get("status")),
                        _md(_run_sources(run)),
                        _md(_run_result(run)),
                        _md(run.get("completed_at")),
                    ]
                )
                + " |"
            )
    else:
        lines.append("No run records are available.")

    lines.append("")
    return "\n".join(lines)


def _prioritized_sources(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(items, key=_source_sort_key)


def _source_sort_key(item: dict[str, Any]) -> tuple[int, int, str]:
    status = str(item.get("last_status") or "")
    failure_type = str(item.get("failure_type") or "none")
    status_rank = 0 if status == "failed" else 1 if not bool(item.get("enabled", True)) else 2
    failure_rank = 0 if failure_type in {"auth", "llm", "storage"} else 1
    return (status_rank, failure_rank, str(item.get("source") or ""))


def _alert_counts(summary: dict[str, Any], alerts: list[dict[str, Any]]) -> dict[str, int]:
    values = summary.get("alert_counts")
    if isinstance(values, dict):
        return {
            "critical": int(values.get("critical", 0) or 0),
            "warning": int(values.get("warning", 0) or 0),
            "info": int(values.get("info", 0) or 0),
            "total": int(values.get("total", len(alerts)) or 0),
        }
    counts = {"critical": 0, "warning": 0, "info": 0, "total": len(alerts)}
    for alert in alerts:
        level = str(alert.get("level") or "info")
        if level in counts:
            counts[level] += 1
    return counts


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _run_sources(run: dict[str, Any]) -> str:
    sources = run.get("metadata", {}).get("sources") if isinstance(run.get("metadata"), dict) else None
    if isinstance(sources, list):
        values = [str(source) for source in sources if str(source)]
        return ", ".join(values[:4]) + ("..." if len(values) > 4 else "")
    return "-"


def _run_result(run: dict[str, Any]) -> str:
    if run.get("error"):
        return str(run.get("error"))
    result = run.get("result")
    if isinstance(result, list):
        selected = sum(int(item.get("selected", 0) or 0) for item in result if isinstance(item, dict))
        analyzed = sum(int(item.get("analyzed", 0) or 0) for item in result if isinstance(item, dict))
        return f"{len(result)} sources, {selected} selected, {analyzed} analyzed"
    return "ok" if result is not None else "-"


def _md(value: Any) -> str:
    text = str(value or "-").replace("\n", " ").replace("|", "\\|").strip()
    return text or "-"


def _stringify_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _display_path(value: Any) -> str:
    text = str(value or "-")
    if text in {"-", "postgres"}:
        return text
    path = Path(text)
    if not path.is_absolute():
        return text
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return f"<external>/{path.name}"
