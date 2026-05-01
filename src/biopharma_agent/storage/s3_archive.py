"""S3-compatible raw archive for MinIO, AWS S3, and compatible services."""

from __future__ import annotations

import importlib
import json
from dataclasses import asdict
from typing import Any

from biopharma_agent.config import RawArchiveSettings
from biopharma_agent.contracts import RawDocument
from biopharma_agent.storage.raw_archive import to_jsonable


class S3RawArchive:
    """Persist raw text and metadata to an S3-compatible bucket."""

    def __init__(self, settings: RawArchiveSettings) -> None:
        if not settings.s3_bucket:
            raise ValueError("S3 raw archive bucket is required")
        self.settings = settings
        self._client = None

    def save(self, raw: RawDocument) -> str:
        prefix = self._object_prefix(raw)
        text_key = f"{prefix}/raw.txt"
        metadata_key = f"{prefix}/metadata.json"
        client = self._s3_client()
        client.put_object(
            Bucket=self.settings.s3_bucket,
            Key=text_key,
            Body=(raw.raw_text or "").encode("utf-8"),
            ContentType="text/plain; charset=utf-8",
        )
        client.put_object(
            Bucket=self.settings.s3_bucket,
            Key=metadata_key,
            Body=json.dumps(to_jsonable(asdict(raw)), ensure_ascii=False, indent=2).encode("utf-8"),
            ContentType="application/json; charset=utf-8",
        )
        return f"s3://{self.settings.s3_bucket}/{text_key}"

    def _object_prefix(self, raw: RawDocument) -> str:
        prefix = self.settings.s3_prefix.strip("/")
        parts = [part for part in [prefix, raw.source.name, raw.document_id] if part]
        return "/".join(_safe_key_part(part) for part in parts)

    def _s3_client(self) -> Any:
        if self._client is not None:
            return self._client
        boto3 = importlib.import_module("boto3")
        kwargs: dict[str, Any] = {}
        if self.settings.s3_endpoint_url:
            kwargs["endpoint_url"] = self.settings.s3_endpoint_url
        if self.settings.s3_access_key_id:
            kwargs["aws_access_key_id"] = self.settings.s3_access_key_id
        if self.settings.s3_secret_access_key:
            kwargs["aws_secret_access_key"] = self.settings.s3_secret_access_key
        if self.settings.s3_region:
            kwargs["region_name"] = self.settings.s3_region
        self._client = boto3.client("s3", **kwargs)
        return self._client


def _safe_key_part(value: str) -> str:
    return value.replace("\\", "-").replace("/", "-").strip()
