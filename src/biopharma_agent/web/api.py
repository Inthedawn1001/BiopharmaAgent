"""Pure API handlers shared by the local server and tests."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from biopharma_agent.agent.planner import LLMTaskPlanner
from biopharma_agent.analytics.brief import IntelligenceBriefBuilder
from biopharma_agent.analytics.report import DeterministicTextAnalytics
from biopharma_agent.analytics.timeseries import TimeSeriesAnalyzer
from biopharma_agent.analysis.pipeline import BiopharmaAnalysisPipeline
from biopharma_agent.collection.runner import CollectionOptions, collect_sources, source_summary
from biopharma_agent.config import AgentSettings
from biopharma_agent.contracts import utc_now
from biopharma_agent.llm.factory import create_llm_provider
from biopharma_agent.ops.diagnostics import diagnose_environment
from biopharma_agent.ops.factory import create_feedback_repository
from biopharma_agent.ops.feedback import FeedbackRecord, LocalFeedbackRepository
from biopharma_agent.ops.source_report import build_source_health_report
from biopharma_agent.orchestration.source_state import source_state_summary
from biopharma_agent.orchestration.scheduler import JobRunRecord, LocalRunLog
from biopharma_agent.sources import get_default_source, get_source_profile, list_default_sources, list_source_profiles
from biopharma_agent.storage.factory import create_analysis_repository, create_source_state_store
from biopharma_agent.storage.local import LocalAnalysisRepository
from biopharma_agent.storage.repository import DocumentFilters


def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "biopharma-agent",
        "features": [
            "deterministic_analysis",
            "llm_analysis",
            "routing",
            "feedback",
            "timeseries",
        ],
    }


def config() -> dict[str, Any]:
    app_settings = AgentSettings.from_env()
    settings = app_settings.llm
    return {
        "provider": settings.provider,
        "base_url": settings.base_url,
        "model": settings.model,
        "has_api_key": bool(settings.api_key),
        "storage_backend": app_settings.storage.backend,
        "analysis_store": app_settings.storage.analysis_jsonl_path
        if app_settings.storage.backend == "jsonl"
        else "postgres",
    }


def diagnostics() -> dict[str, Any]:
    return diagnose_environment()


def list_sources(kind: str = "", category: str = "") -> dict[str, Any]:
    sources = list_default_sources(kind or None, category or None)
    return {
        "items": [source_summary(source) for source in sources],
        "count": len(sources),
    }


def list_profiles() -> dict[str, Any]:
    profiles = list_source_profiles()
    return {
        "items": [profile.to_dict() for profile in profiles],
        "count": len(profiles),
    }


def list_source_state(path: str | Path = "data/runs/source_state.json") -> dict[str, Any]:
    settings = AgentSettings.from_env().storage
    state_path = _safe_workspace_path(path) if settings.backend == "jsonl" else Path("postgres")
    store = create_source_state_store(settings, path=state_path)
    return source_state_summary(
        store,
        sources=list_default_sources(),
        path=str(state_path),
        backend=settings.backend,
    )


def analyze_deterministic(payload: dict[str, Any]) -> dict[str, Any]:
    return DeterministicTextAnalytics().analyze(_require_text(payload))


def analyze_timeseries(payload: dict[str, Any]) -> dict[str, Any]:
    values = payload.get("values")
    if not isinstance(values, list):
        raise ValueError("'values' must be a list of numbers")
    return TimeSeriesAnalyzer().summarize([float(value) for value in values])


def analyze_llm(payload: dict[str, Any]) -> dict[str, Any]:
    provider = create_llm_provider(AgentSettings.from_env().llm)
    return BiopharmaAnalysisPipeline(provider).extract_insight(_require_text(payload))


def route_text(payload: dict[str, Any]) -> dict[str, Any]:
    provider = create_llm_provider(AgentSettings.from_env().llm)
    return LLMTaskPlanner(provider).plan(_require_text(payload))


def append_feedback(payload: dict[str, Any], output: str | Path) -> dict[str, Any]:
    decision = str(payload.get("decision", ""))
    if decision not in {"accept", "reject", "correct"}:
        raise ValueError("decision must be one of: accept, reject, correct")
    record = FeedbackRecord(
        document_id=str(payload.get("document_id", "")),
        reviewer=str(payload.get("reviewer", "")),
        decision=decision,
        comment=str(payload.get("comment", "")),
        corrections=payload.get("corrections", {})
        if isinstance(payload.get("corrections", {}), dict)
        else {},
    )
    if not record.document_id or not record.reviewer or not record.decision:
        raise ValueError("document_id, reviewer, and decision are required")
    settings = AgentSettings.from_env().storage
    if settings.backend == "jsonl":
        repository = LocalFeedbackRepository(_safe_workspace_path(output))
    else:
        repository = create_feedback_repository(settings)
    location = repository.append(record)
    return {"ok": True, "path": str(location), "record": asdict(record)}


def list_jsonl(path: str | Path, limit: int = 50) -> dict[str, Any]:
    target = _safe_workspace_path(path)
    if not target.exists():
        return {"path": str(target), "items": [], "count": 0}
    if limit <= 0:
        raise ValueError("limit must be positive")

    lines = target.read_text(encoding="utf-8").splitlines()
    items: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        if not line.strip():
            continue
        decoded = json.loads(line)
        if isinstance(decoded, dict):
            items.append(decoded)
    return {"path": str(target), "items": items, "count": len(items)}


def list_feedback(path: str | Path, limit: int = 50, offset: int = 0) -> dict[str, Any]:
    settings = AgentSettings.from_env().storage
    if settings.backend == "jsonl":
        repository = LocalFeedbackRepository(_safe_workspace_path(path))
    else:
        repository = create_feedback_repository(settings)
    return repository.list_records(limit=limit, offset=offset)


def list_documents(
    path: str | Path,
    limit: int = 50,
    offset: int = 0,
    source: str = "",
    event_type: str = "",
    risk: str = "",
    query: str = "",
    sort_by: str = "created_at",
    sort_direction: str = "asc",
) -> dict[str, Any]:
    filters = DocumentFilters(
        limit=limit,
        offset=offset,
        source=source,
        event_type=event_type,
        risk=risk,
        query=query,
        sort_by=sort_by,
        sort_direction=sort_direction,
    )
    settings = AgentSettings.from_env().storage
    if settings.backend == "jsonl":
        repository = LocalAnalysisRepository(_safe_workspace_path(path))
    else:
        repository = create_analysis_repository(settings)
    return repository.list_documents(filters).to_dict()


def intelligence_brief(
    path: str | Path = "data/processed/insights.jsonl",
    limit: int = 100,
) -> dict[str, Any]:
    settings = AgentSettings.from_env().storage
    if settings.backend == "jsonl":
        repository = LocalAnalysisRepository(_safe_workspace_path(path))
    else:
        repository = create_analysis_repository(settings)
    records = repository.list_records(limit=max(1, min(int(limit), 500)), offset=0)
    return IntelligenceBriefBuilder().build(records, limit=limit)


def get_document_detail(
    document_id: str,
    path: str | Path,
    source: str = "",
) -> dict[str, Any]:
    settings = AgentSettings.from_env().storage
    if settings.backend == "jsonl":
        repository = LocalAnalysisRepository(_safe_workspace_path(path))
    else:
        repository = create_analysis_repository(settings)
    detail = repository.get_document(document_id=document_id, source=source)
    if detail is None:
        raise ValueError("document not found")
    return detail


def list_runs(path: str | Path, limit: int = 25, offset: int = 0) -> dict[str, Any]:
    run_log = LocalRunLog(_safe_workspace_path(path))
    return run_log.list_records_page(limit=limit, offset=offset)


def source_health_report(
    state_path: str | Path = "data/runs/source_state.json",
    run_log_path: str | Path = "data/runs/fetch_runs.jsonl",
) -> dict[str, Any]:
    source_state = list_source_state(state_path)
    runs = list_runs(run_log_path, limit=5, offset=0)
    return build_source_health_report(source_state, runs)


def trigger_fetch_job(payload: dict[str, Any]) -> dict[str, Any]:
    sources = payload.get("sources")
    profile_name = str(payload.get("profile") or "").strip()
    if isinstance(sources, list) and sources:
        source_names = [str(item) for item in sources if str(item).strip()]
    elif profile_name:
        source_names = get_source_profile(profile_name).source_names
    else:
        source_names = ["fda_press_releases"]
    run_log_path = _safe_workspace_path(str(payload.get("run_log") or "data/runs/fetch_runs.jsonl"))
    storage_settings = AgentSettings.from_env().storage
    state_path = (
        _safe_workspace_path(str(payload.get("state_path") or "data/runs/source_state.json"))
        if storage_settings.backend == "jsonl"
        else Path("postgres")
    )
    options = CollectionOptions(
        limit=max(1, min(int(payload.get("limit", 1)), 25)),
        analyze=_bool_value(payload.get("analyze", True)),
        fetch_details=_bool_value(payload.get("fetch_details", True)),
        clean_html_details=_bool_value(payload.get("clean_html_details", True)),
        archive_dir=_safe_workspace_path(str(payload.get("archive_dir") or "data/raw")),
        output=_safe_workspace_path(str(payload.get("output") or "data/processed/insights.jsonl")),
        graph_dir=_safe_workspace_path(str(payload.get("graph_dir") or "data/graph")),
        no_graph=_bool_value(payload.get("no_graph", False)),
        detail_delay_seconds=float(payload.get("detail_delay_seconds", 0.0)),
        state_path=state_path,
        incremental=_bool_value(payload.get("incremental", False)),
        update_state=_bool_value(payload.get("update_state", True)),
    )
    started_at = utc_now()
    run_id = f"web-{started_at.strftime('%Y%m%d%H%M%S%f')}"
    source_refs = [get_default_source(name) for name in source_names]
    provider = create_llm_provider(AgentSettings.from_env().llm) if options.analyze else None
    try:
        result = collect_sources(sources=source_refs, options=options, provider=provider)
        completed_at = utc_now()
        record = JobRunRecord(
            job_name="web-fetch",
            run_id=run_id,
            status="success",
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=_duration_seconds(started_at, completed_at),
            result=result,
            metadata={
                "sources": source_names,
                "profile": profile_name,
                "limit": options.limit,
                "analyze": options.analyze,
                "fetch_details": options.fetch_details,
                "clean_html_details": options.clean_html_details,
                "incremental": options.incremental,
                "update_state": options.update_state,
                "state_path": str(options.state_path),
            },
        )
    except Exception as exc:
        completed_at = utc_now()
        record = JobRunRecord(
            job_name="web-fetch",
            run_id=run_id,
            status="failed",
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=_duration_seconds(started_at, completed_at),
            error=str(exc),
            metadata={
                "sources": source_names,
                "profile": profile_name,
                "limit": options.limit,
                "analyze": options.analyze,
                "fetch_details": options.fetch_details,
                "clean_html_details": options.clean_html_details,
                "incremental": options.incremental,
                "update_state": options.update_state,
                "state_path": str(options.state_path),
            },
        )
    LocalRunLog(run_log_path).append(record)
    return {"ok": record.status == "success", "record": asdict(record), "run_log": str(run_log_path)}


def _safe_workspace_path(path: str | Path) -> Path:
    root = Path(os.getcwd()).resolve()
    target = Path(path)
    if not target.is_absolute():
        target = root / target
    resolved = target.resolve()
    if not str(resolved).startswith(str(root)):
        raise ValueError("path must stay inside the current workspace")
    return resolved


def _require_text(payload: dict[str, Any]) -> str:
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("'text' is required")
    return text


def _bool_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _duration_seconds(started_at: datetime, completed_at: datetime) -> float:
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=timezone.utc)
    if completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=timezone.utc)
    return max(0.0, (completed_at - started_at).total_seconds())
