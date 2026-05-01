"""Factory helpers for operational repositories."""

from __future__ import annotations

from pathlib import Path

from biopharma_agent.config import StorageSettings
from biopharma_agent.ops.feedback import FeedbackRepository, LocalFeedbackRepository
from biopharma_agent.ops.postgres_feedback import PostgresFeedbackRepository


def create_feedback_repository(
    settings: StorageSettings,
    *,
    path: Path | str | None = None,
) -> FeedbackRepository:
    backend = settings.backend.lower()
    if backend == "jsonl":
        return LocalFeedbackRepository(path or settings.feedback_jsonl_path)
    if backend == "postgres":
        return PostgresFeedbackRepository(settings.postgres_dsn)
    raise ValueError(f"Unsupported storage backend: {settings.backend}")
