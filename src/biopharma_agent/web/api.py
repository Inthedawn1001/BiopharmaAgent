"""Pure API handlers shared by the local server and tests."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from biopharma_agent.agent.planner import LLMTaskPlanner
from biopharma_agent.analytics.brief import IntelligenceBriefBuilder, write_intelligence_brief_artifacts
from biopharma_agent.analytics.report import DeterministicTextAnalytics
from biopharma_agent.analytics.timeseries import TimeSeriesAnalyzer
from biopharma_agent.analysis.pipeline import BiopharmaAnalysisPipeline
from biopharma_agent.collection.runner import CollectionOptions, collect_sources, source_summary
from biopharma_agent.config import AgentSettings
from biopharma_agent.contracts import utc_now
from biopharma_agent.llm.factory import create_llm_provider
from biopharma_agent.llm.types import ChatMessage, LLMRequest
from biopharma_agent.ops.diagnostics import diagnose_environment
from biopharma_agent.ops.factory import create_feedback_repository
from biopharma_agent.ops.feedback import FeedbackRecord, LocalFeedbackRepository
from biopharma_agent.ops.source_report import build_source_health_report
from biopharma_agent.orchestration.source_state import source_state_summary
from biopharma_agent.orchestration.scheduler import JobRunRecord, LocalRunLog
from biopharma_agent.orchestration.daily_cycle import DailyCycleOptions, run_daily_intelligence_cycle
from biopharma_agent.sources import get_default_source, get_source_profile, list_default_sources, list_source_profiles
from biopharma_agent.storage.factory import create_analysis_repository, create_source_state_store
from biopharma_agent.storage.local import LocalAnalysisRepository
from biopharma_agent.storage.repository import DocumentFilters

LLM_PROVIDER_PRESETS: dict[str, dict[str, str]] = {
    "openai": {
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4.1-mini",
    },
    "deepseek": {
        "label": "DeepSeek",
        "provider": "custom",
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat",
    },
    "custom": {
        "label": "OpenAI-compatible",
        "base_url": "http://localhost:8000/v1",
        "model": "model-name",
    },
    "anthropic": {
        "label": "Anthropic",
        "base_url": "https://api.anthropic.com",
        "model": "claude-3-5-sonnet-latest",
    },
    "gemini": {
        "label": "Gemini",
        "base_url": "https://generativelanguage.googleapis.com/v1beta",
        "model": "gemini-1.5-flash",
    },
    "ollama": {
        "label": "Ollama",
        "base_url": "http://localhost:11434",
        "model": "qwen2.5:7b",
    },
    "smoke": {
        "label": "Smoke test",
        "base_url": "local://smoke",
        "model": "smoke-model",
    },
}

_LLM_ENV_KEYS = {
    "provider": "BIOPHARMA_LLM_PROVIDER",
    "base_url": "BIOPHARMA_LLM_BASE_URL",
    "model": "BIOPHARMA_LLM_MODEL",
    "api_key": "BIOPHARMA_LLM_API_KEY",
    "timeout_seconds": "BIOPHARMA_LLM_TIMEOUT_SECONDS",
    "temperature": "BIOPHARMA_LLM_TEMPERATURE",
    "max_tokens": "BIOPHARMA_LLM_MAX_TOKENS",
    "chat_path": "BIOPHARMA_LLM_CHAT_PATH",
}


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
        "timeout_seconds": settings.timeout_seconds,
        "temperature": settings.temperature,
        "max_tokens": settings.max_tokens,
        "chat_path": settings.chat_path or "/chat/completions",
        "presets": LLM_PROVIDER_PRESETS,
        "storage_backend": app_settings.storage.backend,
        "analysis_store": app_settings.storage.analysis_jsonl_path
        if app_settings.storage.backend == "jsonl"
        else "postgres",
    }


def update_llm_config(payload: dict[str, Any]) -> dict[str, Any]:
    """Update the process-local LLM configuration without persisting secrets."""

    provider = str(payload.get("provider") or "").strip().lower()
    if provider:
        if provider == "deepseek":
            provider = "custom"
        if provider not in {"openai", "custom", "anthropic", "gemini", "ollama", "smoke"}:
            raise ValueError("provider must be one of: openai, deepseek, custom, anthropic, gemini, ollama, smoke")
        os.environ[_LLM_ENV_KEYS["provider"]] = provider

    string_fields = {
        "base_url": "base_url",
        "model": "model",
        "chat_path": "chat_path",
    }
    for field, env_field in string_fields.items():
        if field not in payload:
            continue
        value = str(payload.get(field) or "").strip()
        env_key = _LLM_ENV_KEYS[env_field]
        if value:
            os.environ[env_key] = value.rstrip("/") if field == "base_url" else value
        else:
            os.environ.pop(env_key, None)

    numeric_fields = {
        "timeout_seconds": (1.0, 600.0),
        "temperature": (0.0, 2.0),
        "max_tokens": (1.0, 20000.0),
    }
    for field, (minimum, maximum) in numeric_fields.items():
        if field not in payload:
            continue
        raw_value = payload.get(field)
        if raw_value in {"", None}:
            os.environ.pop(_LLM_ENV_KEYS[field], None)
            continue
        value = float(raw_value)
        if value < minimum or value > maximum:
            raise ValueError(f"{field} must be between {minimum:g} and {maximum:g}")
        if field == "max_tokens":
            os.environ[_LLM_ENV_KEYS[field]] = str(int(value))
        else:
            os.environ[_LLM_ENV_KEYS[field]] = str(value)

    if bool(payload.get("clear_api_key")):
        os.environ.pop(_LLM_ENV_KEYS["api_key"], None)
    elif "api_key" in payload:
        api_key = str(payload.get("api_key") or "").strip()
        if api_key:
            os.environ[_LLM_ENV_KEYS["api_key"]] = api_key

    return config()


def llm_config_check() -> dict[str, Any]:
    settings = AgentSettings.from_env().llm
    provider = create_llm_provider(settings)
    response = provider.chat(
        LLMRequest(
            messages=[ChatMessage(role="user", content="Return exactly: ok")],
            max_tokens=8,
            temperature=0,
        )
    )
    return {
        "ok": True,
        "provider": response.provider,
        "model": response.model,
        "finish_reason": response.finish_reason,
        "text_length": len(response.text or ""),
        "has_usage": bool(response.usage),
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
    output_md: str | Path = "",
    output_json: str | Path = "",
) -> dict[str, Any]:
    settings = AgentSettings.from_env().storage
    if settings.backend == "jsonl":
        repository = LocalAnalysisRepository(_safe_workspace_path(path))
    else:
        repository = create_analysis_repository(settings)
    records = repository.list_records(limit=max(1, min(int(limit), 500)), offset=0)
    brief = IntelligenceBriefBuilder().build(records, limit=limit)
    outputs = write_intelligence_brief_artifacts(
        brief,
        markdown_path=_safe_workspace_path(output_md) if output_md else None,
        json_path=_safe_workspace_path(output_json) if output_json else None,
    )
    if outputs:
        brief = dict(brief)
        brief["artifacts"] = outputs
    return brief


def latest_intelligence_brief(
    markdown_path: str | Path = "data/reports/latest_brief.md",
    json_path: str | Path = "data/reports/latest_brief.json",
) -> dict[str, Any]:
    markdown_target = _safe_workspace_path(markdown_path)
    json_target = _safe_workspace_path(json_path)
    brief: dict[str, Any] = {}
    if json_target.exists():
        decoded = json.loads(json_target.read_text(encoding="utf-8") or "{}")
        if not isinstance(decoded, dict):
            raise ValueError("brief JSON artifact must contain an object")
        brief = decoded
    markdown = markdown_target.read_text(encoding="utf-8") if markdown_target.exists() else ""
    if markdown and not brief.get("markdown"):
        brief = dict(brief)
        brief["markdown"] = markdown
    artifacts = {
        "markdown": str(markdown_target),
        "json": str(json_target),
    }
    if brief:
        brief.setdefault("artifacts", artifacts)
    return {
        "ok": bool(brief or markdown),
        "brief": brief,
        "markdown": markdown or str(brief.get("markdown") or ""),
        "artifacts": artifacts,
        "exists": {
            "markdown": markdown_target.exists(),
            "json": json_target.exists(),
        },
        "modified_at": {
            "markdown": _mtime(markdown_target),
            "json": _mtime(json_target),
        },
    }


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


def recommended_sources(
    state_path: str | Path = "data/runs/source_state.json",
    profile: str = "",
    limit: int = 25,
) -> dict[str, Any]:
    source_state = list_source_state(state_path)
    rows_by_source = {str(item.get("source") or ""): item for item in source_state.get("items", [])}
    if profile:
        candidate_names = get_source_profile(profile).source_names
    else:
        candidate_names = [source.name for source in list_default_sources()]
    max_sources = max(1, min(int(limit), 100))
    selected: list[str] = []
    skipped_failed: list[str] = []
    skipped_disabled: list[str] = []
    for name in candidate_names:
        row = rows_by_source.get(name, {})
        if not bool(row.get("enabled", True)):
            skipped_disabled.append(name)
            continue
        if row.get("last_status") == "failed":
            skipped_failed.append(name)
            continue
        selected.append(name)
        if len(selected) >= max_sources:
            break
    return {
        "sources": selected,
        "count": len(selected),
        "profile": profile,
        "state_path": source_state.get("path", str(state_path)),
        "skipped_failed": skipped_failed,
        "skipped_disabled": skipped_disabled,
    }


def trigger_retry_failed_sources(payload: dict[str, Any]) -> dict[str, Any]:
    state_path = str(payload.get("state_path") or "data/runs/source_state.json")
    source_state = list_source_state(state_path)
    requested_sources = payload.get("sources")
    requested = (
        {str(item) for item in requested_sources if str(item).strip()}
        if isinstance(requested_sources, list) and requested_sources
        else set()
    )
    failed_sources = [
        str(item.get("source"))
        for item in source_state.get("items", [])
        if item.get("last_status") == "failed"
        and bool(item.get("enabled", True))
        and (not requested or str(item.get("source")) in requested)
    ]
    if not failed_sources:
        return {
            "ok": True,
            "record": {
                "job_name": "retry-failed-sources",
                "status": "skipped",
                "result": [],
                "metadata": {"sources": [], "state_path": source_state.get("path", state_path)},
            },
            "message": "No failed enabled sources are available for retry.",
            "run_log": str(payload.get("run_log") or "data/runs/fetch_runs.jsonl"),
        }
    retry_payload = dict(payload)
    retry_payload["sources"] = failed_sources
    retry_payload["profile"] = ""
    retry_payload.setdefault("limit", 1)
    retry_payload.setdefault("fetch_details", True)
    retry_payload.setdefault("clean_html_details", True)
    retry_payload.setdefault("incremental", False)
    result = trigger_fetch_job(retry_payload)
    result["retry_sources"] = failed_sources
    return result


def trigger_daily_cycle(payload: dict[str, Any]) -> dict[str, Any]:
    sources = payload.get("sources")
    source_names = [str(item) for item in sources if str(item).strip()] if isinstance(sources, list) else None
    storage_settings = AgentSettings.from_env().storage
    state_path = (
        _safe_workspace_path(str(payload.get("state_path") or "data/runs/source_state.json"))
        if storage_settings.backend == "jsonl"
        else Path("postgres")
    )
    options = DailyCycleOptions(
        profile=str(payload.get("profile") or "core_intelligence"),
        source_names=source_names,
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
        incremental=_bool_value(payload.get("incremental", True)),
        update_state=_bool_value(payload.get("update_state", True)),
        run_log=_safe_workspace_path(str(payload.get("run_log") or "data/runs/daily_cycles.jsonl")),
        brief_limit=max(1, min(int(payload.get("brief_limit", 100)), 500)),
        report_md=_safe_workspace_path(str(payload.get("report_md") or "data/reports/latest_brief.md")),
        report_json=_safe_workspace_path(str(payload.get("report_json") or "data/reports/latest_brief.json")),
    )
    return run_daily_intelligence_cycle(options)


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


def _mtime(path: Path) -> str:
    if not path.exists():
        return ""
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
