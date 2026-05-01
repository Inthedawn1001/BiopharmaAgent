# MinIO Raw Archive

Raw documents are archived through a `RawArchive` protocol. The default backend
is local filesystem storage under `data/raw`. Use MinIO or S3 when raw HTML/PDF
artifacts should be stored in object storage.

## Local MinIO

```bash
python3 -m pip install "boto3>=1.34"
docker compose up -d minio minio-init
export BIOPHARMA_RAW_ARCHIVE_BACKEND=minio
export BIOPHARMA_RAW_ARCHIVE_S3_BUCKET=biopharma-raw
export BIOPHARMA_RAW_ARCHIVE_S3_ENDPOINT_URL=http://127.0.0.1:9000
export BIOPHARMA_RAW_ARCHIVE_S3_ACCESS_KEY_ID=minioadmin
export BIOPHARMA_RAW_ARCHIVE_S3_SECRET_ACCESS_KEY=minioadmin
scripts/run_minio_smoke.sh
```

For the combined PostgreSQL and MinIO smoke used by CI:

```bash
scripts/run_storage_smoke.sh
```

The smoke scripts use `PYTHON` when it is set; otherwise they prefer the active
virtualenv, then `.venv/bin/python`, then `python3`.

The MinIO console is available at `http://127.0.0.1:9001` with the credentials
above.

## AWS S3-Compatible Settings

```bash
export BIOPHARMA_RAW_ARCHIVE_BACKEND=s3
export BIOPHARMA_RAW_ARCHIVE_S3_BUCKET=your-bucket
export BIOPHARMA_RAW_ARCHIVE_S3_PREFIX=raw
export BIOPHARMA_RAW_ARCHIVE_S3_REGION=us-east-1
```

For AWS S3, credentials can come from standard AWS environment variables or the
explicit `BIOPHARMA_RAW_ARCHIVE_S3_ACCESS_KEY_ID` and
`BIOPHARMA_RAW_ARCHIVE_S3_SECRET_ACCESS_KEY` settings.
