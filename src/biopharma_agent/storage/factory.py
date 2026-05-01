"""Factory helpers for selecting storage backends."""

from __future__ import annotations

from pathlib import Path

from biopharma_agent.config import RawArchiveSettings, StorageSettings
from biopharma_agent.storage.local import IdempotentLocalAnalysisRepository, LocalAnalysisRepository
from biopharma_agent.storage.postgres import PostgresAnalysisRepository
from biopharma_agent.storage.raw_archive import LocalRawArchive, RawArchive
from biopharma_agent.storage.repository import AnalysisRepository


def create_analysis_repository(
    settings: StorageSettings,
    *,
    path: Path | str | None = None,
    idempotent: bool = False,
) -> AnalysisRepository:
    """Create the configured analysis repository.

    JSONL stays the default so local development requires no infrastructure.
    PostgreSQL is selected with BIOPHARMA_STORAGE_BACKEND=postgres and
    BIOPHARMA_POSTGRES_DSN.
    """

    backend = settings.backend.lower()
    if backend == "jsonl":
        target = Path(path or settings.analysis_jsonl_path)
        if idempotent:
            return IdempotentLocalAnalysisRepository(target)
        return LocalAnalysisRepository(target)
    if backend == "postgres":
        return PostgresAnalysisRepository(settings.postgres_dsn)
    raise ValueError(f"Unsupported storage backend: {settings.backend}")


def create_raw_archive(
    settings: RawArchiveSettings,
    *,
    path: Path | str | None = None,
) -> RawArchive:
    """Create the configured raw-document archive."""

    backend = settings.backend.lower()
    if backend == "local":
        return LocalRawArchive(path or settings.local_path)
    if backend in {"s3", "minio"}:
        from biopharma_agent.storage.s3_archive import S3RawArchive

        return S3RawArchive(settings)
    raise ValueError(f"Unsupported raw archive backend: {settings.backend}")
