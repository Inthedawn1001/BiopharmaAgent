"""Runtime configuration for the agent."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMSettings:
    """Configuration used to create an LLM provider."""

    provider: str
    base_url: str
    api_key: str | None
    model: str
    chat_path: str | None = None
    embedding_path: str | None = None
    timeout_seconds: float = 60.0
    temperature: float = 0.1
    max_tokens: int = 4000

    @classmethod
    def from_env(cls) -> "LLMSettings":
        provider = os.getenv("BIOPHARMA_LLM_PROVIDER", "openai").strip().lower()
        default_base_url = {
            "openai": "https://api.openai.com/v1",
            "anthropic": "https://api.anthropic.com",
            "gemini": "https://generativelanguage.googleapis.com/v1beta",
            "ollama": "http://localhost:11434",
            "custom": "http://localhost:8000/v1",
            "smoke": "local://smoke",
        }.get(provider, "http://localhost:8000/v1")

        return cls(
            provider=provider,
            base_url=os.getenv("BIOPHARMA_LLM_BASE_URL", default_base_url).rstrip("/"),
            api_key=os.getenv("BIOPHARMA_LLM_API_KEY"),
            model=os.getenv("BIOPHARMA_LLM_MODEL", "gpt-4.1-mini"),
            chat_path=os.getenv("BIOPHARMA_LLM_CHAT_PATH"),
            embedding_path=os.getenv("BIOPHARMA_LLM_EMBEDDING_PATH"),
            timeout_seconds=float(os.getenv("BIOPHARMA_LLM_TIMEOUT_SECONDS", "60")),
            temperature=float(os.getenv("BIOPHARMA_LLM_TEMPERATURE", "0.1")),
            max_tokens=int(os.getenv("BIOPHARMA_LLM_MAX_TOKENS", "4000")),
        )


@dataclass(frozen=True)
class AgentSettings:
    """Top-level settings for the agent process."""

    llm: LLMSettings
    storage: "StorageSettings"
    raw_archive: "RawArchiveSettings"
    graph: "GraphSettings"

    @classmethod
    def from_env(cls) -> "AgentSettings":
        return cls(
            llm=LLMSettings.from_env(),
            storage=StorageSettings.from_env(),
            raw_archive=RawArchiveSettings.from_env(),
            graph=GraphSettings.from_env(),
        )


@dataclass(frozen=True)
class StorageSettings:
    """Configuration for analysis result storage."""

    backend: str
    analysis_jsonl_path: str
    feedback_jsonl_path: str
    source_state_path: str
    postgres_dsn: str

    @classmethod
    def from_env(cls) -> "StorageSettings":
        return cls(
            backend=os.getenv("BIOPHARMA_STORAGE_BACKEND", "jsonl").strip().lower(),
            analysis_jsonl_path=os.getenv(
                "BIOPHARMA_ANALYSIS_JSONL_PATH",
                "data/processed/insights.jsonl",
            ),
            feedback_jsonl_path=os.getenv(
                "BIOPHARMA_FEEDBACK_JSONL_PATH",
                "data/feedback/reviews.jsonl",
            ),
            source_state_path=os.getenv(
                "BIOPHARMA_SOURCE_STATE_PATH",
                "data/runs/source_state.json",
            ),
            postgres_dsn=os.getenv("BIOPHARMA_POSTGRES_DSN", ""),
        )


@dataclass(frozen=True)
class RawArchiveSettings:
    """Configuration for raw document archival."""

    backend: str
    local_path: str
    s3_bucket: str
    s3_prefix: str
    s3_endpoint_url: str
    s3_region: str
    s3_access_key_id: str
    s3_secret_access_key: str

    @classmethod
    def from_env(cls) -> "RawArchiveSettings":
        return cls(
            backend=os.getenv("BIOPHARMA_RAW_ARCHIVE_BACKEND", "local").strip().lower(),
            local_path=os.getenv("BIOPHARMA_RAW_ARCHIVE_PATH", "data/raw"),
            s3_bucket=os.getenv("BIOPHARMA_RAW_ARCHIVE_S3_BUCKET", ""),
            s3_prefix=os.getenv("BIOPHARMA_RAW_ARCHIVE_S3_PREFIX", "raw"),
            s3_endpoint_url=os.getenv("BIOPHARMA_RAW_ARCHIVE_S3_ENDPOINT_URL", ""),
            s3_region=os.getenv("BIOPHARMA_RAW_ARCHIVE_S3_REGION", "us-east-1"),
            s3_access_key_id=os.getenv("BIOPHARMA_RAW_ARCHIVE_S3_ACCESS_KEY_ID", ""),
            s3_secret_access_key=os.getenv("BIOPHARMA_RAW_ARCHIVE_S3_SECRET_ACCESS_KEY", ""),
        )


@dataclass(frozen=True)
class GraphSettings:
    """Configuration for knowledge graph writes."""

    backend: str
    local_path: str
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    neo4j_database: str

    @classmethod
    def from_env(cls) -> "GraphSettings":
        return cls(
            backend=os.getenv("BIOPHARMA_GRAPH_BACKEND", "jsonl").strip().lower(),
            local_path=os.getenv("BIOPHARMA_GRAPH_PATH", "data/graph"),
            neo4j_uri=os.getenv("BIOPHARMA_NEO4J_URI", ""),
            neo4j_user=os.getenv("BIOPHARMA_NEO4J_USER", ""),
            neo4j_password=os.getenv("BIOPHARMA_NEO4J_PASSWORD", ""),
            neo4j_database=os.getenv("BIOPHARMA_NEO4J_DATABASE", "neo4j"),
        )
