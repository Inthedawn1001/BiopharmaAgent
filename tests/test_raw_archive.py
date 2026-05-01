import json
import tempfile
import unittest
from pathlib import Path

from biopharma_agent.config import RawArchiveSettings
from biopharma_agent.contracts import RawDocument, SourceRef
from biopharma_agent.storage.factory import create_raw_archive
from biopharma_agent.storage.raw_archive import LocalRawArchive
from biopharma_agent.storage.s3_archive import S3RawArchive


class RawArchiveTest(unittest.TestCase):
    def test_local_raw_archive_writes_text_and_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            archive = LocalRawArchive(temp_dir)
            raw = _raw_document()

            uri = archive.save(raw)

            self.assertTrue(Path(uri).exists())
            self.assertEqual(Path(uri).read_text(encoding="utf-8"), "raw text")
            metadata = json.loads(
                (Path(temp_dir) / "source" / "doc-1" / "metadata.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(metadata["document_id"], "doc-1")

    def test_factory_selects_local_raw_archive(self):
        archive = create_raw_archive(
            RawArchiveSettings(
                backend="local",
                local_path="data/raw",
                s3_bucket="",
                s3_prefix="",
                s3_endpoint_url="",
                s3_region="",
                s3_access_key_id="",
                s3_secret_access_key="",
            ),
            path="custom/raw",
        )

        self.assertIsInstance(archive, LocalRawArchive)

    def test_s3_raw_archive_writes_text_and_metadata_objects(self):
        settings = RawArchiveSettings(
            backend="minio",
            local_path="data/raw",
            s3_bucket="raw-bucket",
            s3_prefix="archive",
            s3_endpoint_url="http://127.0.0.1:9000",
            s3_region="us-east-1",
            s3_access_key_id="key",
            s3_secret_access_key="secret",
        )
        archive = S3RawArchive(settings)
        archive._client = FakeS3Client()

        uri = archive.save(_raw_document())

        self.assertEqual(uri, "s3://raw-bucket/archive/source/doc-1/raw.txt")
        keys = [call["Key"] for call in archive._client.calls]
        self.assertEqual(keys, ["archive/source/doc-1/raw.txt", "archive/source/doc-1/metadata.json"])
        self.assertEqual(archive._client.calls[0]["Body"], b"raw text")


class FakeS3Client:
    def __init__(self):
        self.calls = []

    def put_object(self, **kwargs):
        self.calls.append(kwargs)


def _raw_document():
    return RawDocument(
        source=SourceRef(name="source", kind="test"),
        document_id="doc-1",
        title="Title",
        raw_text="raw text",
    )


if __name__ == "__main__":
    unittest.main()
