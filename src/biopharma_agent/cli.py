"""Command-line interface for local development and smoke tests."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dataclasses import asdict

from biopharma_agent.agent.planner import LLMTaskPlanner
from biopharma_agent.analytics.brief import IntelligenceBriefBuilder, write_intelligence_brief_artifacts
from biopharma_agent.analytics.report import DeterministicTextAnalytics
from biopharma_agent.analytics.timeseries import TimeSeriesAnalyzer
from biopharma_agent.analysis.pipeline import BiopharmaAnalysisPipeline
from biopharma_agent.collection.runner import CollectionOptions, collect_sources
from biopharma_agent.config import AgentSettings
from biopharma_agent.demo import seed_demo_data
from biopharma_agent.orchestration.scheduler import LocalRunLog, RecurringRunner
from biopharma_agent.orchestration.source_state import source_state_summary
from biopharma_agent.orchestration.workflow import LocalDocumentWorkflow
from biopharma_agent.orchestration.daily_cycle import DailyCycleOptions, run_daily_intelligence_cycle
from biopharma_agent.sources import get_default_source, get_source_profile, list_default_sources, list_source_profiles
from biopharma_agent.storage.local import LocalAnalysisRepository
from biopharma_agent.llm.factory import create_llm_provider
from biopharma_agent.llm.types import ChatMessage, LLMRequest
from biopharma_agent.ops.factory import create_feedback_repository
from biopharma_agent.ops.feedback import FeedbackRecord
from biopharma_agent.ops.diagnostics import diagnose_environment
from biopharma_agent.ops.llm_observer import ObservedLLMProvider
from biopharma_agent.ops.logging import configure_logging
from biopharma_agent.ops.metrics import InMemoryMetrics
from biopharma_agent.ops.quality_gate import run_quality_gate
from biopharma_agent.ops.source_report import build_source_health_report
from biopharma_agent.storage.factory import (
    create_analysis_repository,
    create_graph_writer,
    create_raw_archive,
    create_source_state_store,
)
from biopharma_agent.storage.migrations import PostgresMigrationRunner
from biopharma_agent.web.server import run_server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="biopharma-agent")
    parser.add_argument("--json-logs", action="store_true", help="Emit structured JSON logs.")
    parser.add_argument("--observe-llm", action="store_true", help="Collect local LLM metrics.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("plan", help="Print the current development execution plan.")
    subparsers.add_parser("diagnose", help="Print a secret-safe runtime diagnostics report.")
    subparsers.add_parser("llm-check", help="Send a small health-check request to the LLM.")

    migrate_postgres = subparsers.add_parser(
        "migrate-postgres",
        help="Apply the PostgreSQL schema and record migration version metadata.",
    )
    migrate_postgres.add_argument(
        "--schema",
        type=Path,
        default=Path("infra/postgres/schema.sql"),
        help="Path to schema SQL.",
    )
    migrate_postgres.add_argument(
        "--dsn",
        help="PostgreSQL DSN. Defaults to BIOPHARMA_POSTGRES_DSN.",
    )

    analyze = subparsers.add_parser("analyze-text", help="Analyze text with the configured LLM.")
    input_group = analyze.add_mutually_exclusive_group(required=True)
    input_group.add_argument("--stdin", action="store_true", help="Read text from stdin.")
    input_group.add_argument("--file", type=Path, help="Read text from a local file.")
    analyze.add_argument(
        "--summary-only",
        action="store_true",
        help="Return a free-text summary instead of structured JSON.",
    )

    route = subparsers.add_parser("route-text", help="Ask the LLM which processing steps to run.")
    route_group = route.add_mutually_exclusive_group(required=True)
    route_group.add_argument("--stdin", action="store_true", help="Read text from stdin.")
    route_group.add_argument("--file", type=Path, help="Read text from a local file.")

    deterministic = subparsers.add_parser(
        "analyze-deterministic",
        help="Run local keyword, sentiment, and risk analysis without calling an LLM.",
    )
    deterministic_group = deterministic.add_mutually_exclusive_group(required=True)
    deterministic_group.add_argument("--stdin", action="store_true", help="Read text from stdin.")
    deterministic_group.add_argument("--file", type=Path, help="Read text from a local file.")

    timeseries = subparsers.add_parser(
        "analyze-timeseries",
        help="Summarize numeric market series, e.g. prices or financing amounts.",
    )
    timeseries.add_argument("values", nargs="+", type=float)

    brief = subparsers.add_parser("intelligence-brief", help="Summarize stored analysis results.")
    brief.add_argument("--input", type=Path, default=Path("data/processed/insights.jsonl"))
    brief.add_argument("--limit", type=int, default=100)
    brief.add_argument("--json", action="store_true", help="Print JSON instead of Markdown.")
    brief.add_argument("--output-md", type=Path, help="Write the brief Markdown to this path.")
    brief.add_argument("--output-json", type=Path, help="Write the full brief JSON to this path.")

    feedback = subparsers.add_parser("feedback", help="Append a human review feedback record.")
    feedback.add_argument("--document-id", required=True)
    feedback.add_argument("--reviewer", required=True)
    feedback.add_argument("--decision", required=True, choices=["accept", "reject", "correct"])
    feedback.add_argument("--comment", default="")
    feedback.add_argument("--output", type=Path, default=Path("data/feedback/reviews.jsonl"))

    seed_demo = subparsers.add_parser("seed-demo", help="Write demo records for the workbench.")
    seed_demo.add_argument("--output", type=Path, default=Path("data/processed/insights.jsonl"))
    seed_demo.add_argument(
        "--feedback-output",
        type=Path,
        default=Path("data/feedback/reviews.jsonl"),
    )

    list_sources = subparsers.add_parser("list-sources", help="List built-in sources.")
    list_sources.add_argument("--kind", help="Filter by source kind.")
    list_sources.add_argument("--category", help="Filter by source metadata category.")

    subparsers.add_parser("list-source-profiles", help="List built-in source profiles.")

    source_state = subparsers.add_parser("source-state", help="List source health and incremental state.")
    source_state.add_argument("--state-path", type=Path, default=Path("data/runs/source_state.json"))

    source_report = subparsers.add_parser("source-report", help="Print a Markdown source health report.")
    source_report.add_argument("--state-path", type=Path, default=Path("data/runs/source_state.json"))
    source_report.add_argument("--run-log", type=Path, default=Path("data/runs/fetch_runs.jsonl"))
    source_report.add_argument("--json", action="store_true", help="Print JSON with Markdown and summary.")

    fetch_source = subparsers.add_parser("fetch-source", help="Fetch one built-in RSS/Atom source.")
    fetch_source.add_argument("source")
    fetch_source.add_argument("--limit", type=int, default=5)
    fetch_source.add_argument(
        "--analyze",
        action="store_true",
        help="Analyze each fetched item with the configured LLM and write results.",
    )
    fetch_source.add_argument("--archive-dir", type=Path, default=Path("data/raw"))
    fetch_source.add_argument("--output", type=Path, default=Path("data/processed/insights.jsonl"))
    fetch_source.add_argument("--graph-dir", type=Path, default=Path("data/graph"))
    fetch_source.add_argument("--no-graph", action="store_true", help="Do not write graph JSONL.")
    fetch_source.add_argument("--fetch-details", action="store_true")
    fetch_source.add_argument("--detail-delay-seconds", type=float, default=1.0)
    fetch_source.add_argument("--clean-html-details", action="store_true")
    fetch_source.add_argument("--state-path", type=Path, default=Path("data/runs/source_state.json"))
    fetch_source.add_argument("--incremental", action="store_true")
    fetch_source.add_argument("--no-update-state", action="store_true")

    fetch_sources = subparsers.add_parser(
        "fetch-sources",
        help="Fetch multiple built-in RSS/Atom sources.",
    )
    fetch_sources.add_argument("--profile", help="Source profile name to fetch when --sources is omitted.")
    fetch_sources.add_argument("--sources", nargs="*", help="Source names; defaults to all.")
    fetch_sources.add_argument("--limit", type=int, default=3, help="Items per source.")
    fetch_sources.add_argument("--analyze", action="store_true")
    fetch_sources.add_argument("--archive-dir", type=Path, default=Path("data/raw"))
    fetch_sources.add_argument("--output", type=Path, default=Path("data/processed/insights.jsonl"))
    fetch_sources.add_argument("--graph-dir", type=Path, default=Path("data/graph"))
    fetch_sources.add_argument("--no-graph", action="store_true", help="Do not write graph JSONL.")
    fetch_sources.add_argument("--fetch-details", action="store_true")
    fetch_sources.add_argument("--detail-delay-seconds", type=float, default=1.0)
    fetch_sources.add_argument("--clean-html-details", action="store_true")
    fetch_sources.add_argument("--state-path", type=Path, default=Path("data/runs/source_state.json"))
    fetch_sources.add_argument("--incremental", action="store_true")
    fetch_sources.add_argument("--no-update-state", action="store_true")

    fetch_html_source = subparsers.add_parser(
        "fetch-html-source",
        help="Fetch one built-in HTML listing source.",
    )
    fetch_html_source.add_argument("source")
    fetch_html_source.add_argument("--limit", type=int, default=5)
    fetch_html_source.add_argument("--analyze", action="store_true")
    fetch_html_source.add_argument("--fetch-details", action="store_true")
    fetch_html_source.add_argument("--detail-delay-seconds", type=float, default=1.0)
    fetch_html_source.add_argument(
        "--clean-html-details",
        action="store_true",
        help="Use main-content text instead of full raw HTML for fetched detail pages.",
    )
    fetch_html_source.add_argument("--archive-dir", type=Path, default=Path("data/raw"))
    fetch_html_source.add_argument("--output", type=Path, default=Path("data/processed/insights.jsonl"))
    fetch_html_source.add_argument("--graph-dir", type=Path, default=Path("data/graph"))
    fetch_html_source.add_argument("--no-graph", action="store_true", help="Do not write graph JSONL.")
    fetch_html_source.add_argument("--state-path", type=Path, default=Path("data/runs/source_state.json"))
    fetch_html_source.add_argument("--incremental", action="store_true")
    fetch_html_source.add_argument("--no-update-state", action="store_true")

    fetch_html_sources = subparsers.add_parser(
        "fetch-html-sources",
        help="Fetch multiple built-in HTML listing sources.",
    )
    fetch_html_sources.add_argument("--sources", nargs="*", help="Source names; defaults to all HTML sources.")
    fetch_html_sources.add_argument("--limit", type=int, default=5)
    fetch_html_sources.add_argument("--analyze", action="store_true")
    fetch_html_sources.add_argument("--fetch-details", action="store_true")
    fetch_html_sources.add_argument("--detail-delay-seconds", type=float, default=1.0)
    fetch_html_sources.add_argument(
        "--clean-html-details",
        action="store_true",
        help="Use main-content text instead of full raw HTML for fetched detail pages.",
    )
    fetch_html_sources.add_argument("--archive-dir", type=Path, default=Path("data/raw"))
    fetch_html_sources.add_argument("--output", type=Path, default=Path("data/processed/insights.jsonl"))
    fetch_html_sources.add_argument("--graph-dir", type=Path, default=Path("data/graph"))
    fetch_html_sources.add_argument("--no-graph", action="store_true", help="Do not write graph JSONL.")
    fetch_html_sources.add_argument("--state-path", type=Path, default=Path("data/runs/source_state.json"))
    fetch_html_sources.add_argument("--incremental", action="store_true")
    fetch_html_sources.add_argument("--no-update-state", action="store_true")

    scheduled_fetch = subparsers.add_parser(
        "scheduled-fetch",
        help="Run fetch-sources once or repeatedly with a local JSONL run log.",
    )
    scheduled_fetch.add_argument("--profile", help="Source profile name to fetch when --sources is omitted.")
    scheduled_fetch.add_argument("--sources", nargs="*", help="Source names; defaults to all.")
    scheduled_fetch.add_argument("--limit", type=int, default=3, help="Items per source.")
    scheduled_fetch.add_argument("--analyze", action="store_true")
    scheduled_fetch.add_argument("--fetch-details", action="store_true")
    scheduled_fetch.add_argument("--detail-delay-seconds", type=float, default=1.0)
    scheduled_fetch.add_argument("--clean-html-details", action="store_true")
    scheduled_fetch.add_argument("--interval-seconds", type=float, default=3600)
    scheduled_fetch.add_argument(
        "--max-runs",
        type=int,
        default=1,
        help="Number of runs before exiting. Use 0 to run until interrupted.",
    )
    scheduled_fetch.add_argument("--archive-dir", type=Path, default=Path("data/raw"))
    scheduled_fetch.add_argument("--output", type=Path, default=Path("data/processed/insights.jsonl"))
    scheduled_fetch.add_argument("--graph-dir", type=Path, default=Path("data/graph"))
    scheduled_fetch.add_argument("--run-log", type=Path, default=Path("data/runs/fetch_runs.jsonl"))
    scheduled_fetch.add_argument("--no-graph", action="store_true", help="Do not write graph JSONL.")
    scheduled_fetch.add_argument("--state-path", type=Path, default=Path("data/runs/source_state.json"))
    scheduled_fetch.add_argument("--incremental", action="store_true")
    scheduled_fetch.add_argument("--no-update-state", action="store_true")
    scheduled_fetch.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop recurring execution after the first failed run.",
    )

    daily_cycle = subparsers.add_parser(
        "daily-cycle",
        help="Run the full fetch, analysis, source-state, and intelligence brief cycle once.",
    )
    daily_cycle.add_argument("--profile", default="core_intelligence")
    daily_cycle.add_argument("--sources", nargs="*", help="Explicit source names; overrides --profile.")
    daily_cycle.add_argument("--limit", type=int, default=1, help="Items per source.")
    daily_cycle.add_argument("--analyze", action=argparse.BooleanOptionalAction, default=True)
    daily_cycle.add_argument("--fetch-details", action=argparse.BooleanOptionalAction, default=True)
    daily_cycle.add_argument("--clean-html-details", action=argparse.BooleanOptionalAction, default=True)
    daily_cycle.add_argument("--archive-dir", type=Path, default=Path("data/raw"))
    daily_cycle.add_argument("--output", type=Path, default=Path("data/processed/insights.jsonl"))
    daily_cycle.add_argument("--graph-dir", type=Path, default=Path("data/graph"))
    daily_cycle.add_argument("--no-graph", action="store_true", help="Do not write graph JSONL.")
    daily_cycle.add_argument("--detail-delay-seconds", type=float, default=0.0)
    daily_cycle.add_argument("--state-path", type=Path, default=Path("data/runs/source_state.json"))
    daily_cycle.add_argument("--incremental", action=argparse.BooleanOptionalAction, default=True)
    daily_cycle.add_argument("--no-update-state", action="store_true")
    daily_cycle.add_argument("--run-log", type=Path, default=Path("data/runs/daily_cycles.jsonl"))
    daily_cycle.add_argument("--brief-limit", type=int, default=100)
    daily_cycle.add_argument("--report-md", type=Path, default=Path("data/reports/latest_brief.md"))
    daily_cycle.add_argument("--report-json", type=Path, default=Path("data/reports/latest_brief.json"))
    daily_cycle.add_argument("--json", action="store_true", help="Print the full cycle JSON result.")

    quality_gate = subparsers.add_parser(
        "quality-gate",
        help="Validate local intelligence artifacts before operational use.",
    )
    quality_gate.add_argument("--analysis-path", type=Path, default=Path("data/processed/insights.jsonl"))
    quality_gate.add_argument("--brief-md", type=Path, default=Path("data/reports/latest_brief.md"))
    quality_gate.add_argument("--source-state", type=Path, default=Path("data/runs/source_state.json"))
    quality_gate.add_argument("--min-records", type=int, default=1)
    quality_gate.add_argument("--min-summary-ratio", type=float, default=0.8)
    quality_gate.add_argument("--min-event-ratio", type=float, default=0.6)
    quality_gate.add_argument("--min-risk-ratio", type=float, default=0.6)
    quality_gate.add_argument("--min-usable-body-ratio", type=float, default=0.5)
    quality_gate.add_argument("--max-failed-sources", type=int, default=0)
    quality_gate.add_argument("--require-brief", action="store_true")
    quality_gate.add_argument("--require-source-state", action="store_true")
    quality_gate.add_argument("--json", action="store_true", help="Print the full gate result as JSON.")

    serve = subparsers.add_parser("serve", help="Start the local web workbench.")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--quiet", action="store_true", help="Reduce request logging.")

    run_local = subparsers.add_parser(
        "run-local",
        help="Run archive, parse, LLM analysis, and local JSONL storage for one document.",
    )
    run_group = run_local.add_mutually_exclusive_group(required=True)
    run_group.add_argument("--stdin", action="store_true", help="Read text from stdin.")
    run_group.add_argument("--file", type=Path, help="Read text from a local file.")
    run_local.add_argument("--source-name", default="manual")
    run_local.add_argument("--title")
    run_local.add_argument("--url")
    run_local.add_argument("--archive-dir", type=Path, default=Path("data/raw"))
    run_local.add_argument("--output", type=Path, default=Path("data/processed/insights.jsonl"))
    run_local.add_argument("--graph-dir", type=Path, default=Path("data/graph"))
    run_local.add_argument("--no-graph", action="store_true", help="Do not write graph JSONL.")
    run_local.add_argument(
        "--append-duplicates",
        action="store_true",
        help="Append duplicate JSONL rows instead of replacing an existing result with the same key.",
    )

    run_url = subparsers.add_parser(
        "run-url",
        help="Fetch a URL, parse it, run LLM analysis, and write local outputs.",
    )
    run_url.add_argument("url")
    run_url.add_argument("--source-name")
    run_url.add_argument("--archive-dir", type=Path, default=Path("data/raw"))
    run_url.add_argument("--output", type=Path, default=Path("data/processed/insights.jsonl"))
    run_url.add_argument("--graph-dir", type=Path, default=Path("data/graph"))
    run_url.add_argument("--no-graph", action="store_true", help="Do not write graph JSONL.")
    run_url.add_argument(
        "--append-duplicates",
        action="store_true",
        help="Append duplicate JSONL rows instead of replacing an existing result with the same key.",
    )
    run_url.add_argument(
        "--ignore-robots",
        action="store_true",
        help="Disable robots.txt checks. Use only for permitted internal sources.",
    )

    args = parser.parse_args(argv)

    if args.json_logs:
        configure_logging()

    if args.command == "plan":
        _print_plan()
        return 0

    if args.command == "diagnose":
        print(json.dumps(diagnose_environment(), ensure_ascii=False, indent=2))
        return 0

    if args.command == "migrate-postgres":
        dsn = args.dsn or AgentSettings.from_env().storage.postgres_dsn
        results = PostgresMigrationRunner(dsn, schema_path=args.schema).migrate_all()
        print(
            json.dumps(
                {
                    "migrations": [result.to_dict() for result in results],
                    "applied": sum(1 for result in results if result.status == "applied"),
                    "skipped": sum(1 for result in results if result.status == "skipped"),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "analyze-deterministic":
        text = sys.stdin.read() if args.stdin else args.file.read_text(encoding="utf-8")
        print(json.dumps(DeterministicTextAnalytics().analyze(text), ensure_ascii=False, indent=2))
        return 0

    if args.command == "analyze-timeseries":
        print(json.dumps(TimeSeriesAnalyzer().summarize(args.values), ensure_ascii=False, indent=2))
        return 0

    if args.command == "feedback":
        settings = AgentSettings.from_env()
        location = create_feedback_repository(settings.storage, path=args.output).append(
            FeedbackRecord(
                document_id=args.document_id,
                reviewer=args.reviewer,
                decision=args.decision,
                comment=args.comment,
            )
        )
        print(str(location))
        return 0

    if args.command == "seed-demo":
        print(
            json.dumps(
                seed_demo_data(output=args.output, feedback_output=args.feedback_output),
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "list-sources":
        print(
            json.dumps(
                [asdict(source) for source in list_default_sources(args.kind, args.category)],
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "list-source-profiles":
        print(
            json.dumps(
                [profile.to_dict() for profile in list_source_profiles()],
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "source-state":
        storage_settings = AgentSettings.from_env().storage
        store = create_source_state_store(storage_settings, path=args.state_path)
        state_path = str(args.state_path) if storage_settings.backend == "jsonl" else "postgres"
        state = source_state_summary(
            store,
            sources=list_default_sources(),
            path=state_path,
            backend=storage_settings.backend,
        )
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0

    if args.command == "source-report":
        storage_settings = AgentSettings.from_env().storage
        store = create_source_state_store(storage_settings, path=args.state_path)
        state_path = str(args.state_path) if storage_settings.backend == "jsonl" else "postgres"
        state = source_state_summary(
            store,
            sources=list_default_sources(),
            path=state_path,
            backend=storage_settings.backend,
        )
        runs = LocalRunLog(args.run_log).list_records_page(limit=5, offset=0)
        report = build_source_health_report(state, runs)
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(report["markdown"])
        return 0

    if args.command == "intelligence-brief":
        repository = LocalAnalysisRepository(args.input)
        report = IntelligenceBriefBuilder().build(repository.list_records(limit=args.limit), limit=args.limit)
        outputs = write_intelligence_brief_artifacts(
            report,
            markdown_path=args.output_md,
            json_path=args.output_json,
        )
        if outputs and not args.json:
            artifact_lines = ["", "## Artifacts", ""]
            artifact_lines.extend(f"- {label}: {path}" for label, path in outputs.items())
            report = dict(report)
            report["markdown"] = report["markdown"] + "\n".join(artifact_lines) + "\n"
        if args.json:
            if outputs:
                report = dict(report)
                report["artifacts"] = outputs
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(report["markdown"])
        return 0

    if args.command == "serve":
        run_server(host=args.host, port=args.port, quiet=args.quiet)
        return 0

    needs_llm = args.command in {
        "llm-check",
        "analyze-text",
        "route-text",
        "run-local",
        "run-url",
    } or (
        args.command in {
            "fetch-source",
            "fetch-sources",
            "fetch-html-source",
            "fetch-html-sources",
            "scheduled-fetch",
            "daily-cycle",
        }
        and args.analyze
    )
    provider = None
    if needs_llm:
        settings = AgentSettings.from_env()
        provider = create_llm_provider(settings.llm)
    else:
        settings = None
    metrics = InMemoryMetrics()
    if args.observe_llm and provider is not None:
        provider = ObservedLLMProvider(provider, metrics)

    if args.command == "llm-check":
        assert provider is not None
        response = provider.chat(
            LLMRequest(
                messages=[
                    ChatMessage(role="system", content="You are a terse health-check endpoint."),
                    ChatMessage(role="user", content="Reply with: ok"),
                ],
                max_tokens=16,
                temperature=0,
            )
        )
        print(response.text.strip())
        if args.observe_llm:
            print(json.dumps(metrics.snapshot(), ensure_ascii=False, indent=2))
        return 0

    if args.command == "analyze-text":
        assert provider is not None
        text = sys.stdin.read() if args.stdin else args.file.read_text(encoding="utf-8")
        pipeline = BiopharmaAnalysisPipeline(provider)
        if args.summary_only:
            print(pipeline.summarize(text))
        else:
            print(json.dumps(pipeline.extract_insight(text), ensure_ascii=False, indent=2))
        return 0

    if args.command == "route-text":
        assert provider is not None
        text = sys.stdin.read() if args.stdin else args.file.read_text(encoding="utf-8")
        planner = LLMTaskPlanner(provider)
        print(json.dumps(planner.plan(text), ensure_ascii=False, indent=2))
        return 0

    if args.command == "run-local":
        assert provider is not None
        assert settings is not None
        text = sys.stdin.read() if args.stdin else args.file.read_text(encoding="utf-8")
        workflow = LocalDocumentWorkflow(
            llm=provider,
            raw_archive=create_raw_archive(settings.raw_archive, path=args.archive_dir),
            analysis_repository=create_analysis_repository(
                settings.storage,
                path=args.output,
                idempotent=not args.append_duplicates,
            ),
            graph_writer=None if args.no_graph else create_graph_writer(settings.graph, path=args.graph_dir),
        )
        result = workflow.run_text(
            text=text,
            source_name=args.source_name,
            title=args.title,
            url=args.url,
        )
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "run-url":
        assert provider is not None
        assert settings is not None
        from biopharma_agent.collection.http_fetcher import HTTPSourceFetcher

        workflow = LocalDocumentWorkflow(
            llm=provider,
            raw_archive=create_raw_archive(settings.raw_archive, path=args.archive_dir),
            analysis_repository=create_analysis_repository(
                settings.storage,
                path=args.output,
                idempotent=not args.append_duplicates,
            ),
            graph_writer=None if args.no_graph else create_graph_writer(settings.graph, path=args.graph_dir),
        )
        result = workflow.run_url(
            args.url,
            source_name=args.source_name,
            fetcher=HTTPSourceFetcher(respect_robots_txt=not args.ignore_robots),
        )
        print(json.dumps(asdict(result), ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "fetch-source":
        source = get_default_source(args.source)
        summary = _fetch_and_optionally_analyze_sources(
            sources=[source],
            limit=args.limit,
            analyze=args.analyze,
            provider=provider,
            archive_dir=args.archive_dir,
            output=args.output,
            graph_dir=args.graph_dir,
            no_graph=args.no_graph,
            fetch_details=args.fetch_details,
            detail_delay_seconds=args.detail_delay_seconds,
            clean_html_details=args.clean_html_details,
            state_path=args.state_path,
            incremental=args.incremental,
            update_state=not args.no_update_state,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "fetch-sources":
        source_names = _resolve_source_names(source_names=args.sources, profile_name=args.profile)
        sources = [get_default_source(name) for name in source_names]
        summary = _fetch_and_optionally_analyze_sources(
            sources=sources,
            limit=args.limit,
            analyze=args.analyze,
            provider=provider,
            archive_dir=args.archive_dir,
            output=args.output,
            graph_dir=args.graph_dir,
            no_graph=args.no_graph,
            fetch_details=args.fetch_details,
            detail_delay_seconds=args.detail_delay_seconds,
            clean_html_details=args.clean_html_details,
            state_path=args.state_path,
            incremental=args.incremental,
            update_state=not args.no_update_state,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "fetch-html-source":
        source = get_default_source(args.source)
        summary = _fetch_and_optionally_analyze_html_sources(
            sources=[source],
            limit=args.limit,
            analyze=args.analyze,
            provider=provider,
            archive_dir=args.archive_dir,
            output=args.output,
            graph_dir=args.graph_dir,
            no_graph=args.no_graph,
            fetch_details=args.fetch_details,
            detail_delay_seconds=args.detail_delay_seconds,
            clean_html_details=args.clean_html_details,
            state_path=args.state_path,
            incremental=args.incremental,
            update_state=not args.no_update_state,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "fetch-html-sources":
        source_names = args.sources or [
            source.name
            for source in list_default_sources()
            if source.metadata.get("collector") == "html_listing"
            and source.metadata.get("enabled", True)
        ]
        sources = [get_default_source(name) for name in source_names]
        summary = _fetch_and_optionally_analyze_html_sources(
            sources=sources,
            limit=args.limit,
            analyze=args.analyze,
            provider=provider,
            archive_dir=args.archive_dir,
            output=args.output,
            graph_dir=args.graph_dir,
            no_graph=args.no_graph,
            fetch_details=args.fetch_details,
            detail_delay_seconds=args.detail_delay_seconds,
            clean_html_details=args.clean_html_details,
            state_path=args.state_path,
            incremental=args.incremental,
            update_state=not args.no_update_state,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "scheduled-fetch":
        max_runs = None if args.max_runs == 0 else args.max_runs
        runner = RecurringRunner(LocalRunLog(args.run_log))
        source_names = _resolve_source_names(source_names=args.sources, profile_name=args.profile)
        selected_profile = "" if args.sources else (args.profile or "")

        def job():
            return run_fetch_sources_job(
                source_names=source_names,
                limit=args.limit,
                analyze=args.analyze,
                archive_dir=args.archive_dir,
                output=args.output,
                graph_dir=args.graph_dir,
                no_graph=args.no_graph,
                fetch_details=args.fetch_details,
                detail_delay_seconds=args.detail_delay_seconds,
                clean_html_details=args.clean_html_details,
                state_path=args.state_path,
                incremental=args.incremental,
                update_state=not args.no_update_state,
                profile_name=args.profile,
            )

        records = runner.run_forever(
            "fetch-sources",
            job,
            interval_seconds=args.interval_seconds,
            max_runs=max_runs,
            stop_on_error=args.stop_on_error,
            metadata={
                "sources": source_names,
                "profile": selected_profile,
                "limit": args.limit,
                "analyze": args.analyze,
                "fetch_details": args.fetch_details,
                "clean_html_details": args.clean_html_details,
                "incremental": args.incremental,
                "update_state": not args.no_update_state,
                "state_path": str(args.state_path),
            },
        )
        print(json.dumps([asdict(record) for record in records], ensure_ascii=False, indent=2, default=str))
        return 0

    if args.command == "daily-cycle":
        result = run_daily_intelligence_cycle(
            DailyCycleOptions(
                profile=args.profile,
                source_names=args.sources,
                limit=args.limit,
                analyze=args.analyze,
                fetch_details=args.fetch_details,
                clean_html_details=args.clean_html_details,
                archive_dir=args.archive_dir,
                output=args.output,
                graph_dir=args.graph_dir,
                no_graph=args.no_graph,
                detail_delay_seconds=args.detail_delay_seconds,
                state_path=args.state_path,
                incremental=args.incremental,
                update_state=not args.no_update_state,
                run_log=args.run_log,
                brief_limit=args.brief_limit,
                report_md=args.report_md,
                report_json=args.report_json,
            ),
            provider=provider,
        )
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        else:
            record = result["record"]
            brief = record.get("result", {}).get("brief", {}) if isinstance(record.get("result"), dict) else {}
            print(f"Daily intelligence cycle {record['status']}: {record['run_id']}")
            if record.get("error"):
                print(f"Error: {record['error']}")
            if brief:
                print(f"Documents: {brief.get('document_count', 0)}")
                print(f"Summary: {brief.get('summary', '')}")
                artifacts = brief.get("artifacts") if isinstance(brief.get("artifacts"), dict) else {}
                for label, path in artifacts.items():
                    print(f"{label}: {path}")
        return 0

    if args.command == "quality-gate":
        result = run_quality_gate(
            analysis_path=args.analysis_path,
            brief_markdown_path=args.brief_md,
            source_state_path=args.source_state,
            min_records=args.min_records,
            min_summary_ratio=args.min_summary_ratio,
            min_event_ratio=args.min_event_ratio,
            min_risk_ratio=args.min_risk_ratio,
            min_usable_body_ratio=args.min_usable_body_ratio,
            max_failed_sources=args.max_failed_sources,
            require_brief=args.require_brief,
            require_source_state=args.require_source_state,
        )
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"Quality gate {result['status']}: {result['summary']['passed']}/{result['summary']['total']} checks passed")
            for check in result["checks"]:
                marker = "OK" if check["status"] == "pass" else "FAIL"
                print(f"- {marker} {check['name']}: {check['message']}")
        return 0 if result["status"] == "pass" else 1

    parser.error(f"Unknown command: {args.command}")
    return 2


def _print_plan() -> None:
    plan = [
        "Phase 1: LLM provider abstraction and structured extraction MVP. [done]",
        "Phase 2: local document contracts, raw archive, parsing, and checksum support. [done]",
        "Phase 3: feed source registry and RSS/Atom collection. [in progress]",
        "Phase 4: repository abstraction, JSONL idempotency, PostgreSQL SQL listing, feedback storage, raw archive abstraction, and compose integration. [in progress]",
        "Phase 5: NLP, topic modeling, SQL analytics, time-series analysis, and risk scoring. [next]",
        "Phase 6: scheduling, observability, evaluation, human review, and deployment packaging. [next]",
    ]
    for item in plan:
        print(f"- {item}")


def _fetch_and_optionally_analyze_sources(
    sources,
    limit: int,
    analyze: bool,
    provider,
    archive_dir: Path,
    output: Path,
    graph_dir: Path,
    no_graph: bool,
    fetch_details: bool = False,
    detail_delay_seconds: float = 1.0,
    clean_html_details: bool = False,
    state_path: Path = Path("data/runs/source_state.json"),
    incremental: bool = False,
    update_state: bool = True,
) -> list[dict[str, object]]:
    return collect_sources(
        sources=sources,
        options=CollectionOptions(
            limit=limit,
            analyze=analyze,
            fetch_details=fetch_details,
            clean_html_details=clean_html_details,
            archive_dir=archive_dir,
            output=output,
            graph_dir=graph_dir,
            no_graph=no_graph,
            detail_delay_seconds=detail_delay_seconds,
            state_path=state_path,
            incremental=incremental,
            update_state=update_state,
        ),
        provider=provider,
    )


def _fetch_and_optionally_analyze_html_sources(
    sources,
    limit: int,
    analyze: bool,
    provider,
    archive_dir: Path,
    output: Path,
    graph_dir: Path,
    no_graph: bool,
    fetch_details: bool = False,
    detail_delay_seconds: float = 1.0,
    clean_html_details: bool = False,
    state_path: Path = Path("data/runs/source_state.json"),
    incremental: bool = False,
    update_state: bool = True,
) -> list[dict[str, object]]:
    for source in sources:
        if source.metadata.get("collector") != "html_listing":
            raise ValueError(f"Source {source.name} is not configured as an HTML listing source")
    return _fetch_and_optionally_analyze_sources(
        sources=sources,
        limit=limit,
        analyze=analyze,
        provider=provider,
        archive_dir=archive_dir,
        output=output,
        graph_dir=graph_dir,
        no_graph=no_graph,
        fetch_details=fetch_details,
        detail_delay_seconds=detail_delay_seconds,
        clean_html_details=clean_html_details,
        state_path=state_path,
        incremental=incremental,
        update_state=update_state,
    )


def run_fetch_sources_job(
    *,
    source_names: list[str] | None,
    limit: int,
    analyze: bool,
    archive_dir: Path,
    output: Path,
    graph_dir: Path,
    no_graph: bool,
    fetch_details: bool = False,
    detail_delay_seconds: float = 1.0,
    clean_html_details: bool = False,
    state_path: Path = Path("data/runs/source_state.json"),
    incremental: bool = False,
    update_state: bool = True,
    profile_name: str | None = None,
) -> list[dict[str, object]]:
    settings = AgentSettings.from_env()
    provider = create_llm_provider(settings.llm) if analyze else None
    names = _resolve_source_names(source_names=source_names, profile_name=profile_name)
    sources = [get_default_source(name) for name in names]
    return _fetch_and_optionally_analyze_sources(
        sources=sources,
        limit=limit,
        analyze=analyze,
        provider=provider,
        archive_dir=archive_dir,
        output=output,
        graph_dir=graph_dir,
        no_graph=no_graph,
        fetch_details=fetch_details,
        detail_delay_seconds=detail_delay_seconds,
        clean_html_details=clean_html_details,
        state_path=state_path,
        incremental=incremental,
        update_state=update_state,
    )


def _resolve_source_names(
    *,
    source_names: list[str] | None = None,
    profile_name: str | None = None,
) -> list[str]:
    if source_names:
        return [name for name in source_names if name]
    if profile_name:
        return get_source_profile(profile_name).source_names
    return [source.name for source in list_default_sources()]


if __name__ == "__main__":
    raise SystemExit(main())
