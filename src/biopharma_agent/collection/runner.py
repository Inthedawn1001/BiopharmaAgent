"""Unified collection dispatcher shared by CLI, scheduler, and web jobs."""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from biopharma_agent.collection.asx import ASXAnnouncementsFetcher
from biopharma_agent.collection.feed import FeedFetcher
from biopharma_agent.collection.html_listing import HTMLListingFetcher
from biopharma_agent.collection.http_fetcher import HTTPSourceFetcher
from biopharma_agent.collection.sec import SECSubmissionsFetcher
from biopharma_agent.config import AgentSettings
from biopharma_agent.contracts import RawDocument, SourceRef, utc_now
from biopharma_agent.llm.base import LLMProvider
from biopharma_agent.orchestration.source_state import SourceStateStore
from biopharma_agent.orchestration.workflow import LocalDocumentWorkflow
from biopharma_agent.storage.factory import (
    create_analysis_repository,
    create_graph_writer,
    create_raw_archive,
    create_source_state_store,
)


@dataclass(frozen=True)
class CollectionOptions:
    limit: int = 1
    analyze: bool = False
    fetch_details: bool = False
    clean_html_details: bool = False
    archive_dir: Path = Path("data/raw")
    output: Path = Path("data/processed/insights.jsonl")
    graph_dir: Path = Path("data/graph")
    no_graph: bool = False
    detail_delay_seconds: float = 1.0
    state_path: Path = Path("data/runs/source_state.json")
    incremental: bool = False
    update_state: bool = True


def collect_sources(
    *,
    sources: list[SourceRef],
    options: CollectionOptions,
    provider: LLMProvider | None = None,
) -> list[dict[str, Any]]:
    workflow = _workflow(options, provider)
    state_store = _source_state_store(options)
    summaries: list[dict[str, Any]] = []
    for source in sources:
        summaries.append(
            collect_source(
                source=source,
                options=options,
                workflow=workflow,
                state_store=state_store,
            )
        )
    return summaries


def collect_source(
    *,
    source: SourceRef,
    options: CollectionOptions,
    workflow: LocalDocumentWorkflow | None = None,
    state_store: SourceStateStore | None = None,
) -> dict[str, Any]:
    started_at = utc_now()
    if state_store is None and options.update_state:
        state_store = _source_state_store(options)
    if not source.metadata.get("enabled", True):
        raise ValueError(
            f"Source {source.name} is disabled: {source.metadata.get('disabled_reason', 'no reason provided')}"
        )
    try:
        request_delay = float(source.metadata.get("request_delay_seconds", 0) or 0)
        if request_delay > 0:
            time.sleep(request_delay)

        collector = str(source.metadata.get("collector") or "feed")
        if collector == "html_listing":
            summary, raw_documents = _collect_html_listing(source, options)
        elif collector == "asx_announcements":
            summary, raw_documents = _collect_asx(source, options)
        elif collector == "sec_submissions":
            summary, raw_documents = _collect_sec(source, options)
        else:
            summary, raw_documents = _collect_feed(source, options)

        raw_documents, skipped_seen = _filter_seen_documents(
            source=source,
            documents=raw_documents,
            options=options,
            state_store=state_store,
        )
        summary["selected"] = len(raw_documents)
        if int(summary.get("details_fetched", 0) or 0) > 0:
            summary["details_fetched"] = len(raw_documents)
        summary["incremental"] = options.incremental
        summary["skipped_seen"] = skipped_seen
        summary["state_path"] = str(options.state_path) if options.update_state else ""

        analyzed = 0
        if workflow:
            for raw in raw_documents:
                workflow.run_raw(raw)
                analyzed += 1
        summary["analyzed"] = analyzed
        if state_store:
            state = state_store.record_success(
                source,
                started_at=started_at,
                completed_at=utc_now(),
                summary=summary,
                documents=raw_documents,
            )
            summary["source_state"] = _compact_state(state)
        return summary
    except Exception as exc:
        if state_store:
            state_store.record_failure(
                source,
                started_at=started_at,
                completed_at=utc_now(),
                error=str(exc),
            )
        raise


def source_summary(source: SourceRef) -> dict[str, Any]:
    return {
        "name": source.name,
        "kind": source.kind,
        "url": source.url,
        "collector": source.metadata.get("collector", "feed"),
        "category": source.metadata.get("category", ""),
        "priority": source.metadata.get("priority", 100),
        "enabled": source.metadata.get("enabled", True),
        "disabled_reason": source.metadata.get("disabled_reason", ""),
        "metadata": source.metadata,
    }


def _collect_feed(
    source: SourceRef,
    options: CollectionOptions,
) -> tuple[dict[str, Any], list[RawDocument]]:
    result = FeedFetcher().fetch(source)
    raw_documents = (
        result.fetch_detail_documents(
            HTTPSourceFetcher(respect_robots_txt=bool(source.metadata.get("respect_robots_txt", True))),
            limit=options.limit,
            detail_delay_seconds=options.detail_delay_seconds,
            clean_html=options.clean_html_details,
            sleep=time.sleep,
        )
        if options.fetch_details
        else result.to_raw_documents(limit=options.limit)
    )
    return (
        {
            "source": source.name,
            "kind": source.kind,
            "collector": "feed",
            "category": source.metadata.get("category", ""),
            "priority": source.metadata.get("priority", 100),
            "feed_url": result.feed_url,
            "fetched": len(result.items),
            "selected": len(raw_documents),
            "details_fetched": len(raw_documents) if options.fetch_details else 0,
            "clean_html_details": bool(options.fetch_details and options.clean_html_details),
            "items": [
                {"title": item.title, "link": item.link, "published": item.published}
                for item in result.items[: options.limit]
            ],
        },
        raw_documents,
    )


def _collect_html_listing(
    source: SourceRef,
    options: CollectionOptions,
) -> tuple[dict[str, Any], list[RawDocument]]:
    result = HTMLListingFetcher().fetch(source)
    raw_documents = (
        result.fetch_detail_documents(
            HTTPSourceFetcher(respect_robots_txt=bool(source.metadata.get("respect_robots_txt", True))),
            limit=options.limit,
            detail_delay_seconds=options.detail_delay_seconds,
            clean_html=options.clean_html_details,
            sleep=time.sleep,
        )
        if options.fetch_details
        else result.to_raw_documents(limit=options.limit)
    )
    return (
        {
            "source": source.name,
            "kind": source.kind,
            "collector": "html_listing",
            "category": source.metadata.get("category", ""),
            "priority": source.metadata.get("priority", 100),
            "listing_url": result.listing_url,
            "status_code": result.status_code,
            "fetched": len(result.links),
            "selected": len(raw_documents),
            "details_fetched": len(raw_documents) if options.fetch_details else 0,
            "clean_html_details": bool(options.fetch_details and options.clean_html_details),
            "items": [{"title": item.title, "link": item.url} for item in result.links[: options.limit]],
        },
        raw_documents,
    )


def _collect_asx(
    source: SourceRef,
    options: CollectionOptions,
) -> tuple[dict[str, Any], list[RawDocument]]:
    result = ASXAnnouncementsFetcher().fetch(source)
    raw_documents = result.to_raw_documents(limit=options.limit)
    return (
        {
            "source": source.name,
            "kind": source.kind,
            "collector": "asx_announcements",
            "category": source.metadata.get("category", ""),
            "priority": source.metadata.get("priority", 100),
            "status_code": result.status_code,
            "searched_tickers": result.searched_tickers,
            "fetched": len(result.announcements),
            "selected": len(raw_documents),
            "details_fetched": 0,
            "clean_html_details": False,
            "items": [
                {
                    "title": item.title,
                    "link": item.url,
                    "ticker": item.ticker,
                    "released_at": item.released_at,
                }
                for item in result.announcements[: options.limit]
            ],
        },
        raw_documents,
    )


def _collect_sec(
    source: SourceRef,
    options: CollectionOptions,
) -> tuple[dict[str, Any], list[RawDocument]]:
    result = SECSubmissionsFetcher().fetch(source)
    raw_documents = result.to_raw_documents(
        limit=options.limit,
        fetch_details=options.fetch_details,
        clean_html=options.clean_html_details,
        fetcher=HTTPSourceFetcher(respect_robots_txt=False),
    )
    return (
        {
            "source": source.name,
            "kind": source.kind,
            "collector": "sec_submissions",
            "category": source.metadata.get("category", ""),
            "priority": source.metadata.get("priority", 100),
            "status_code": result.status_code,
            "searched_ciks": result.searched_ciks,
            "errors": result.errors or [],
            "fetched": len(result.filings),
            "selected": len(raw_documents),
            "details_fetched": len(raw_documents) if options.fetch_details else 0,
            "clean_html_details": bool(options.fetch_details and options.clean_html_details),
            "items": [
                {
                    "title": f"{item.company} {item.form} {item.filing_date}".strip(),
                    "link": item.document_url,
                    "form": item.form,
                    "cik": item.cik,
                    "filing_date": item.filing_date,
                }
                for item in result.filings[: options.limit]
            ],
        },
        raw_documents,
    )


def _workflow(
    options: CollectionOptions,
    provider: LLMProvider | None,
) -> LocalDocumentWorkflow | None:
    if not options.analyze:
        return None
    if provider is None:
        raise RuntimeError("LLM provider is required when analyze is enabled")
    settings = AgentSettings.from_env()
    return LocalDocumentWorkflow(
        llm=provider,
        raw_archive=create_raw_archive(settings.raw_archive, path=options.archive_dir),
        analysis_repository=create_analysis_repository(
            settings.storage,
            path=options.output,
            idempotent=True,
        ),
        graph_writer=None if options.no_graph else create_graph_writer(settings.graph, path=options.graph_dir),
    )


def _filter_seen_documents(
    *,
    source: SourceRef,
    documents: list[RawDocument],
    options: CollectionOptions,
    state_store: SourceStateStore | None,
) -> tuple[list[RawDocument], int]:
    if not options.incremental or not state_store:
        return documents, 0
    seen = state_store.seen_document_ids(source.name)
    selected = [document for document in documents if document.document_id not in seen]
    return selected, len(documents) - len(selected)


def _compact_state(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "last_status": record.get("last_status", ""),
        "last_completed_at": record.get("last_completed_at", ""),
        "seen_count": record.get("seen_count", 0),
        "consecutive_failures": record.get("consecutive_failures", 0),
    }


def _source_state_store(options: CollectionOptions) -> SourceStateStore | None:
    if not options.update_state:
        return None
    settings = AgentSettings.from_env()
    return create_source_state_store(settings.storage, path=options.state_path)
