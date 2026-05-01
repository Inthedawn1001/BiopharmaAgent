"""Dependency-free local web server for the analyst workbench."""

from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from biopharma_agent.web import api

STATIC_DIR = Path(__file__).with_name("static")


class WorkbenchRequestHandler(BaseHTTPRequestHandler):
    server_version = "BiopharmaAgentWorkbench/0.1"

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self._write_json(api.health())
            return

        if parsed.path == "/api/config":
            self._write_json(api.config())
            return

        if parsed.path == "/api/diagnostics":
            self._write_json(api.diagnostics())
            return

        if parsed.path == "/api/sources":
            query = parse_qs(parsed.query)
            self._write_json(
                api.list_sources(
                    kind=query.get("kind", [""])[0],
                    category=query.get("category", [""])[0],
                )
            )
            return

        if parsed.path == "/api/source-profiles":
            self._write_json(api.list_profiles())
            return

        if parsed.path == "/api/documents":
            query = parse_qs(parsed.query)
            path = query.get("path", ["data/processed/insights.jsonl"])[0]
            limit = int(query.get("limit", ["50"])[0])
            offset = int(query.get("offset", ["0"])[0])
            self._write_json(
                api.list_documents(
                    path,
                    limit=limit,
                    offset=offset,
                    source=query.get("source", [""])[0],
                    event_type=query.get("event_type", [""])[0],
                    risk=query.get("risk", [""])[0],
                    query=query.get("query", [""])[0],
                    sort_by=query.get("sort_by", ["created_at"])[0],
                    sort_direction=query.get("sort_direction", ["asc"])[0],
                )
            )
            return

        if parsed.path == "/api/intelligence-brief":
            query = parse_qs(parsed.query)
            path = query.get("path", ["data/processed/insights.jsonl"])[0]
            limit = int(query.get("limit", ["100"])[0])
            self._write_json(
                api.intelligence_brief(
                    path,
                    limit=limit,
                    output_md=query.get("output_md", [""])[0],
                    output_json=query.get("output_json", [""])[0],
                )
            )
            return

        if parsed.path == "/api/intelligence-brief/latest":
            query = parse_qs(parsed.query)
            self._write_json(
                api.latest_intelligence_brief(
                    markdown_path=query.get("markdown_path", ["data/reports/latest_brief.md"])[0],
                    json_path=query.get("json_path", ["data/reports/latest_brief.json"])[0],
                )
            )
            return

        if parsed.path.startswith("/api/documents/"):
            query = parse_qs(parsed.query)
            path = query.get("path", ["data/processed/insights.jsonl"])[0]
            document_id = unquote(parsed.path.removeprefix("/api/documents/"))
            source = query.get("source", [""])[0]
            try:
                self._write_json(api.get_document_detail(document_id, path=path, source=source))
            except ValueError as exc:
                self._write_json(
                    {"error": "not_found", "message": str(exc)},
                    HTTPStatus.NOT_FOUND,
                )
            return

        if parsed.path == "/api/feedback":
            query = parse_qs(parsed.query)
            path = query.get("path", ["data/feedback/reviews.jsonl"])[0]
            limit = int(query.get("limit", ["50"])[0])
            offset = int(query.get("offset", ["0"])[0])
            self._write_json(api.list_feedback(path, limit=limit, offset=offset))
            return

        if parsed.path == "/api/runs":
            query = parse_qs(parsed.query)
            path = query.get("path", ["data/runs/fetch_runs.jsonl"])[0]
            limit = int(query.get("limit", ["25"])[0])
            offset = int(query.get("offset", ["0"])[0])
            self._write_json(api.list_runs(path, limit=limit, offset=offset))
            return

        if parsed.path == "/api/source-state":
            query = parse_qs(parsed.query)
            path = query.get("path", ["data/runs/source_state.json"])[0]
            self._write_json(api.list_source_state(path))
            return

        if parsed.path == "/api/source-report":
            query = parse_qs(parsed.query)
            state_path = query.get("state_path", ["data/runs/source_state.json"])[0]
            run_log = query.get("run_log", ["data/runs/fetch_runs.jsonl"])[0]
            self._write_json(api.source_health_report(state_path, run_log))
            return

        if parsed.path == "/api/sources/recommended":
            query = parse_qs(parsed.query)
            self._write_json(
                api.recommended_sources(
                    state_path=query.get("state_path", ["data/runs/source_state.json"])[0],
                    profile=query.get("profile", [""])[0],
                    limit=int(query.get("limit", ["25"])[0]),
                )
            )
            return

        if parsed.path.startswith("/api/"):
            self._write_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
            return

        self._serve_static(parsed.path)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        try:
            payload = self._read_json()
            if parsed.path == "/api/analyze/deterministic":
                self._write_json(api.analyze_deterministic(payload))
                return

            if parsed.path == "/api/analyze/timeseries":
                self._write_json(api.analyze_timeseries(payload))
                return

            if parsed.path == "/api/analyze/llm":
                self._write_json(api.analyze_llm(payload))
                return

            if parsed.path == "/api/route":
                self._write_json(api.route_text(payload))
                return

            if parsed.path == "/api/feedback":
                output = query.get("output", ["data/feedback/reviews.jsonl"])[0]
                self._write_json(api.append_feedback(payload, output))
                return

            if parsed.path == "/api/jobs/fetch":
                result = api.trigger_fetch_job(payload)
                self._write_json(
                    result,
                    HTTPStatus.OK if result.get("ok") else HTTPStatus.BAD_REQUEST,
                )
                return

            if parsed.path == "/api/jobs/daily-cycle":
                result = api.trigger_daily_cycle(payload)
                self._write_json(
                    result,
                    HTTPStatus.OK if result.get("ok") else HTTPStatus.BAD_REQUEST,
                )
                return

            if parsed.path == "/api/jobs/retry-failed":
                result = api.trigger_retry_failed_sources(payload)
                self._write_json(
                    result,
                    HTTPStatus.OK if result.get("ok") else HTTPStatus.BAD_REQUEST,
                )
                return

            self._write_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            self._write_json({"error": "bad_request", "message": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            self._write_json(
                {"error": "server_error", "message": str(exc)},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def log_message(self, format: str, *args: Any) -> None:
        if getattr(self.server, "quiet", False):
            return
        super().log_message(format, *args)

    def _read_json(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        if content_length <= 0:
            return {}
        raw = self.rfile.read(content_length).decode("utf-8")
        decoded = json.loads(raw)
        if not isinstance(decoded, dict):
            raise ValueError("JSON body must be an object")
        return decoded

    def _write_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _serve_static(self, request_path: str) -> None:
        relative = request_path.lstrip("/") or "index.html"
        if relative.endswith("/"):
            relative += "index.html"
        target = (STATIC_DIR / relative).resolve()
        if not str(target).startswith(str(STATIC_DIR.resolve())) or not target.exists():
            target = STATIC_DIR / "index.html"

        content_type = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        body = target.read_bytes()
        self.send_response(HTTPStatus.OK.value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def create_server(host: str = "127.0.0.1", port: int = 8765, quiet: bool = False) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), WorkbenchRequestHandler)
    server.quiet = quiet  # type: ignore[attr-defined]
    return server


def run_server(host: str = "127.0.0.1", port: int = 8765, quiet: bool = False) -> None:
    server = create_server(host=host, port=port, quiet=quiet)
    url = f"http://{host}:{server.server_port}"
    print(f"Biopharma Agent workbench running at {url}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping workbench server.")
    finally:
        server.server_close()
