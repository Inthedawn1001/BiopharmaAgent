"""Smoke-test S3/MinIO raw archive with one synthetic raw document."""

from __future__ import annotations

from biopharma_agent.config import RawArchiveSettings
from biopharma_agent.contracts import RawDocument, SourceRef
from biopharma_agent.storage.s3_archive import S3RawArchive


def main() -> int:
    settings = RawArchiveSettings.from_env()
    archive = S3RawArchive(settings)
    uri = archive.save(
        RawDocument(
            source=SourceRef(name="s3_smoke", kind="integration"),
            document_id="s3-smoke-doc",
            title="S3 Smoke Document",
            raw_text="Synthetic raw document for S3/MinIO smoke testing.",
        )
    )
    print({"raw_uri": uri})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
