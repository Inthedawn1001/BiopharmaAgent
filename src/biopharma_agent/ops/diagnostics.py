"""Runtime diagnostics for local development and deployment smoke checks."""

from __future__ import annotations

import importlib.util
import os
import platform
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from biopharma_agent.config import AgentSettings
from biopharma_agent.sources import list_default_sources


def diagnose_environment(workspace: Path | str | None = None) -> dict[str, Any]:
    """Return a secret-safe snapshot of runtime readiness."""

    root = Path(workspace or Path.cwd()).resolve()
    settings = AgentSettings.from_env()
    checks = {
        "python": _python_check(),
        "llm": _llm_check(settings),
        "storage": _storage_check(settings, root),
        "raw_archive": _raw_archive_check(settings, root),
        "sources": _sources_check(),
        "docker": _docker_check(root),
        "git": _git_check(root),
    }
    return {
        "status": _overall_status(checks),
        "workspace": str(root),
        "checks": checks,
    }


def _python_check() -> dict[str, Any]:
    optional_dependencies = {
        "boto3": importlib.util.find_spec("boto3") is not None,
        "psycopg": importlib.util.find_spec("psycopg") is not None,
    }
    return {
        "status": "ok",
        "version": platform.python_version(),
        "executable": sys.executable,
        "optional_dependencies": optional_dependencies,
    }


def _llm_check(settings: AgentSettings) -> dict[str, Any]:
    llm = settings.llm
    api_key_required = llm.provider in {"openai", "anthropic", "gemini", "custom"}
    issues: list[str] = []
    if api_key_required and not llm.api_key:
        issues.append("BIOPHARMA_LLM_API_KEY is not configured.")
    if not llm.model:
        issues.append("BIOPHARMA_LLM_MODEL is empty.")
    if not llm.base_url:
        issues.append("BIOPHARMA_LLM_BASE_URL is empty.")

    return {
        "status": "ok" if not issues else "warning",
        "provider": llm.provider,
        "model": llm.model,
        "base_url": llm.base_url,
        "has_api_key": bool(llm.api_key),
        "api_key_required": api_key_required,
        "chat_path": llm.chat_path or "/chat/completions",
        "timeout_seconds": llm.timeout_seconds,
        "issues": issues,
    }


def _storage_check(settings: AgentSettings, root: Path) -> dict[str, Any]:
    storage = settings.storage
    issues: list[str] = []
    details: dict[str, Any] = {"backend": storage.backend}
    if storage.backend == "jsonl":
        analysis_path = _workspace_path(root, storage.analysis_jsonl_path)
        feedback_path = _workspace_path(root, storage.feedback_jsonl_path)
        details.update(
            {
                "analysis_jsonl_path": str(analysis_path),
                "feedback_jsonl_path": str(feedback_path),
                "analysis_parent_ready": _parent_ready(analysis_path),
                "feedback_parent_ready": _parent_ready(feedback_path),
            }
        )
    elif storage.backend == "postgres":
        has_driver = importlib.util.find_spec("psycopg") is not None
        details.update(
            {
                "has_dsn": bool(storage.postgres_dsn),
                "driver_available": has_driver,
            }
        )
        if not storage.postgres_dsn:
            issues.append("BIOPHARMA_POSTGRES_DSN is not configured.")
        if not has_driver:
            issues.append("psycopg is not installed in this Python environment.")
    else:
        issues.append(f"Unsupported storage backend: {storage.backend}")

    details["status"] = "ok" if not issues else "warning"
    details["issues"] = issues
    return details


def _raw_archive_check(settings: AgentSettings, root: Path) -> dict[str, Any]:
    archive = settings.raw_archive
    issues: list[str] = []
    details: dict[str, Any] = {"backend": archive.backend}
    if archive.backend == "local":
        local_path = _workspace_path(root, archive.local_path)
        details.update(
            {
                "path": str(local_path),
                "parent_ready": _parent_ready(local_path),
            }
        )
    elif archive.backend in {"s3", "minio"}:
        has_boto3 = importlib.util.find_spec("boto3") is not None
        details.update(
            {
                "bucket": archive.s3_bucket,
                "prefix": archive.s3_prefix,
                "endpoint_url": archive.s3_endpoint_url,
                "region": archive.s3_region,
                "has_access_key": bool(archive.s3_access_key_id),
                "has_secret_key": bool(archive.s3_secret_access_key),
                "driver_available": has_boto3,
            }
        )
        if not archive.s3_bucket:
            issues.append("BIOPHARMA_RAW_ARCHIVE_S3_BUCKET is not configured.")
        if not has_boto3:
            issues.append("boto3 is not installed in this Python environment.")
    else:
        issues.append(f"Unsupported raw archive backend: {archive.backend}")

    details["status"] = "ok" if not issues else "warning"
    details["issues"] = issues
    return details


def _sources_check() -> dict[str, Any]:
    sources = list_default_sources()
    enabled = [source for source in sources if source.metadata.get("enabled", True)]
    disabled = [source for source in sources if not source.metadata.get("enabled", True)]
    collectors = Counter(str(source.metadata.get("collector", "feed")) for source in sources)
    categories = Counter(str(source.metadata.get("category", "unknown")) for source in sources)
    return {
        "status": "ok" if enabled else "warning",
        "total": len(sources),
        "enabled": len(enabled),
        "disabled": len(disabled),
        "collectors": dict(sorted(collectors.items())),
        "categories": dict(sorted(categories.items())),
        "enabled_sources": [source.name for source in enabled],
        "disabled_sources": [
            {
                "name": source.name,
                "reason": source.metadata.get("disabled_reason", ""),
            }
            for source in disabled
        ],
    }


def _docker_check(root: Path) -> dict[str, Any]:
    docker_path = _find_docker()
    if not docker_path:
        return {
            "status": "warning",
            "available": False,
            "issues": ["Docker CLI was not found in PATH or ~/Applications/Docker.app."],
        }

    env = os.environ.copy()
    docker_dir = str(Path(docker_path).parent)
    env["PATH"] = f"{docker_dir}{os.pathsep}{env.get('PATH', '')}"
    version = _run_command(
        [docker_path, "version", "--format", "{{.Client.Version}} / {{.Server.Version}}"],
        cwd=root,
        env=env,
    )
    compose = _run_command([docker_path, "compose", "version"], cwd=root, env=env)
    issues: list[str] = []
    if version["returncode"] != 0:
        issues.append(version["stderr"] or version["stdout"] or "Docker daemon is not ready.")
    if compose["returncode"] != 0:
        issues.append(compose["stderr"] or compose["stdout"] or "Docker Compose is not ready.")

    return {
        "status": "ok" if not issues else "warning",
        "available": not issues,
        "cli_path": docker_path,
        "version": version["stdout"],
        "compose_version": compose["stdout"],
        "issues": issues,
    }


def _git_check(root: Path) -> dict[str, Any]:
    inside = _run_command(["git", "rev-parse", "--is-inside-work-tree"], cwd=root)
    if inside["returncode"] != 0 or inside["stdout"] != "true":
        return {
            "status": "warning",
            "inside_work_tree": False,
            "issues": ["Current workspace is not a git repository."],
        }

    branch = _run_command(["git", "branch", "--show-current"], cwd=root)
    head = _run_command(["git", "rev-parse", "HEAD"], cwd=root)
    status = _run_command(["git", "status", "--short"], cwd=root)
    remote = _run_command(["git", "remote", "get-url", "origin"], cwd=root)
    upstream = _run_command(["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"], cwd=root)
    remote_head = _run_command(["git", "ls-remote", "--heads", "origin", branch["stdout"] or "main"], cwd=root, timeout=5)

    pending_changes = [line for line in status["stdout"].splitlines() if line.strip()]
    issues: list[str] = []
    remote_url = remote["stdout"] if remote["returncode"] == 0 else ""
    remote_commit = ""
    if not remote_url:
        issues.append("No git remote named origin is configured.")
    elif remote_head["returncode"] != 0:
        issues.append(remote_head["stderr"] or "Could not read origin branch.")
    elif remote_head["stdout"]:
        remote_commit = remote_head["stdout"].split()[0]
        if head["stdout"] and remote_commit != head["stdout"]:
            issues.append("Local HEAD does not match origin branch.")
    else:
        issues.append("Origin branch is empty or not created yet.")
    if upstream["returncode"] != 0:
        issues.append("No upstream branch is configured for the current branch.")
    if pending_changes:
        issues.append("Workspace has uncommitted changes.")

    return {
        "status": "ok" if not issues else "warning",
        "inside_work_tree": True,
        "branch": branch["stdout"],
        "head": head["stdout"],
        "origin": remote_url,
        "upstream": upstream["stdout"] if upstream["returncode"] == 0 else "",
        "origin_head": remote_commit,
        "pending_changes": len(pending_changes),
        "issues": issues,
    }


def _overall_status(checks: dict[str, dict[str, Any]]) -> str:
    statuses = {check.get("status", "warning") for check in checks.values()}
    if "failed" in statuses:
        return "failed"
    if "warning" in statuses:
        return "warning"
    return "ok"


def _find_docker() -> str:
    found = shutil.which("docker")
    if found:
        return found
    bundled = Path.home() / "Applications/Docker.app/Contents/Resources/bin/docker"
    if bundled.exists():
        return str(bundled)
    return ""


def _run_command(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str] | None = None,
    timeout: float = 3,
) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return {
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
    except FileNotFoundError as exc:
        return {"returncode": 127, "stdout": "", "stderr": str(exc)}
    except subprocess.TimeoutExpired:
        return {"returncode": 124, "stdout": "", "stderr": "command timed out"}


def _workspace_path(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def _parent_ready(path: Path) -> bool:
    parent = path if path.is_dir() else path.parent
    if parent.exists():
        return os.access(parent, os.W_OK)
    nearest = parent
    while not nearest.exists() and nearest.parent != nearest:
        nearest = nearest.parent
    return nearest.exists() and os.access(nearest, os.W_OK)
