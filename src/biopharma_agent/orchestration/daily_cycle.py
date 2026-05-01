"""End-to-end daily intelligence cycle orchestration."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from biopharma_agent.analytics.brief import IntelligenceBriefBuilder, write_intelligence_brief_artifacts
from biopharma_agent.collection.runner import CollectionOptions, collect_sources
from biopharma_agent.config import AgentSettings
from biopharma_agent.contracts import utc_now
from biopharma_agent.llm.base import LLMProvider
from biopharma_agent.llm.factory import create_llm_provider
from biopharma_agent.orchestration.scheduler import JobRunRecord, LocalRunLog
from biopharma_agent.sources import get_default_source, get_source_profile, list_default_sources
from biopharma_agent.storage.factory import create_analysis_repository
from biopharma_agent.storage.local import LocalAnalysisRepository


@dataclass(frozen=True)
class DailyCycleOptions:
    """Options for a repeatable fetch, analysis, and brief-generation cycle."""

    profile: str = "core_intelligence"
    source_names: list[str] | None = None
    limit: int = 1
    analyze: bool = True
    fetch_details: bool = True
    clean_html_details: bool = True
    archive_dir: Path = Path("data/raw")
    output: Path = Path("data/processed/insights.jsonl")
    graph_dir: Path = Path("data/graph")
    no_graph: bool = False
    detail_delay_seconds: float = 0.0
    state_path: Path = Path("data/runs/source_state.json")
    incremental: bool = True
    update_state: bool = True
    run_log: Path = Path("data/runs/daily_cycles.jsonl")
    brief_limit: int = 100
    report_md: Path = Path("data/reports/latest_brief.md")
    report_json: Path = Path("data/reports/latest_brief.json")


def run_daily_intelligence_cycle(
    options: DailyCycleOptions,
    *,
    provider: LLMProvider | None = None,
    settings: AgentSettings | None = None,
) -> dict[str, Any]:
    """Run the full daily cycle and always append a structured run record."""

    settings = settings or AgentSettings.from_env()
    started_at = utc_now()
    run_id = f"daily-{started_at.strftime('%Y%m%d%H%M%S%f')}"
    source_names = resolve_cycle_source_names(options.source_names, options.profile)
    metadata = _cycle_metadata(options, source_names)
    try:
        llm_provider = provider
        if options.analyze and llm_provider is None:
            llm_provider = create_llm_provider(settings.llm)

        fetch_result = collect_sources(
            sources=[get_default_source(name) for name in source_names],
            options=CollectionOptions(
                limit=max(1, min(int(options.limit), 25)),
                analyze=options.analyze,
                fetch_details=options.fetch_details,
                clean_html_details=options.clean_html_details,
                archive_dir=options.archive_dir,
                output=options.output,
                graph_dir=options.graph_dir,
                no_graph=options.no_graph,
                detail_delay_seconds=options.detail_delay_seconds,
                state_path=options.state_path,
                incremental=options.incremental,
                update_state=options.update_state,
            ),
            provider=llm_provider,
        )
        brief = _build_brief(settings, options)
        artifacts = write_intelligence_brief_artifacts(
            brief,
            markdown_path=options.report_md,
            json_path=options.report_json,
        )
        if artifacts:
            brief = dict(brief)
            brief["artifacts"] = artifacts
        result = {
            "sources": source_names,
            "fetch": fetch_result,
            "brief": _compact_brief(brief),
        }
        completed_at = utc_now()
        record = JobRunRecord(
            job_name="daily-intelligence-cycle",
            run_id=run_id,
            status="success",
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=_duration_seconds(started_at, completed_at),
            result=result,
            metadata=metadata,
        )
    except Exception as exc:
        completed_at = utc_now()
        record = JobRunRecord(
            job_name="daily-intelligence-cycle",
            run_id=run_id,
            status="failed",
            started_at=started_at,
            completed_at=completed_at,
            duration_seconds=_duration_seconds(started_at, completed_at),
            error=str(exc),
            metadata=metadata,
        )
    LocalRunLog(options.run_log).append(record)
    return {
        "ok": record.status == "success",
        "record": asdict(record),
        "run_log": str(options.run_log),
    }


def resolve_cycle_source_names(source_names: list[str] | None, profile: str = "") -> list[str]:
    if source_names:
        return [name for name in source_names if name]
    if profile:
        return get_source_profile(profile).source_names
    return [source.name for source in list_default_sources() if source.metadata.get("enabled", True)]


def _build_brief(settings: AgentSettings, options: DailyCycleOptions) -> dict[str, Any]:
    if settings.storage.backend == "jsonl":
        repository = LocalAnalysisRepository(options.output)
    else:
        repository = create_analysis_repository(settings.storage)
    records = repository.list_records(limit=max(1, min(int(options.brief_limit), 500)), offset=0)
    return IntelligenceBriefBuilder().build(records, limit=options.brief_limit)


def _compact_brief(brief: dict[str, Any]) -> dict[str, Any]:
    return {
        "generated_at": brief.get("generated_at", ""),
        "document_count": brief.get("document_count", 0),
        "summary": brief.get("summary", ""),
        "event_counts": brief.get("event_counts", []),
        "risk_counts": brief.get("risk_counts", []),
        "top_terms": brief.get("top_terms", []),
        "artifacts": brief.get("artifacts", {}),
    }


def _cycle_metadata(options: DailyCycleOptions, source_names: list[str]) -> dict[str, Any]:
    data = asdict(options)
    data["source_names"] = source_names
    for key in ["archive_dir", "output", "graph_dir", "state_path", "run_log", "report_md", "report_json"]:
        data[key] = str(data[key])
    return data


def _duration_seconds(started_at: datetime, completed_at: datetime) -> float:
    return max(0.0, (completed_at - started_at).total_seconds())
