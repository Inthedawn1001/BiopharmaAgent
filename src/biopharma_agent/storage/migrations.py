"""PostgreSQL schema migration runner."""

from __future__ import annotations

import hashlib
import importlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DEFAULT_SCHEMA_PATH = Path("infra/postgres/schema.sql")
DEFAULT_MIGRATION_ID = "0001_initial_schema"


@dataclass(frozen=True)
class MigrationResult:
    migration_id: str
    status: str
    checksum: str
    schema_path: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class PostgresMigrationRunner:
    """Apply the project PostgreSQL schema once and record its checksum."""

    def __init__(
        self,
        dsn: str,
        *,
        schema_path: Path | str = DEFAULT_SCHEMA_PATH,
        migration_id: str = DEFAULT_MIGRATION_ID,
        connect_timeout: int = 10,
    ) -> None:
        if not dsn:
            raise ValueError("PostgreSQL DSN is required")
        self.dsn = dsn
        self.schema_path = Path(schema_path)
        self.migration_id = migration_id
        self.connect_timeout = connect_timeout

    def migrate(self) -> MigrationResult:
        schema_sql = self.schema_path.read_text(encoding="utf-8")
        checksum = hashlib.sha256(schema_sql.encode("utf-8")).hexdigest()

        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(_MIGRATION_TABLE_SQL)
                cursor.execute(
                    "select checksum from schema_migrations where migration_id = %s",
                    (self.migration_id,),
                )
                row = cursor.fetchone()
                if row:
                    existing_checksum = row[0]
                    if existing_checksum != checksum:
                        raise ValueError(
                            "PostgreSQL migration checksum mismatch for "
                            f"{self.migration_id}: expected {existing_checksum}, got {checksum}"
                        )
                    connection.commit()
                    return MigrationResult(
                        migration_id=self.migration_id,
                        status="skipped",
                        checksum=checksum,
                        schema_path=str(self.schema_path),
                    )

                cursor.execute(schema_sql)
                cursor.execute(
                    """
                    insert into schema_migrations (migration_id, checksum)
                    values (%s, %s)
                    """,
                    (self.migration_id, checksum),
                )
            connection.commit()

        return MigrationResult(
            migration_id=self.migration_id,
            status="applied",
            checksum=checksum,
            schema_path=str(self.schema_path),
        )

    def _connect(self) -> Any:
        psycopg = importlib.import_module("psycopg")
        return psycopg.connect(self.dsn, connect_timeout=self.connect_timeout)


_MIGRATION_TABLE_SQL = """
create table if not exists schema_migrations (
    migration_id text primary key,
    checksum text not null,
    applied_at timestamptz not null default now()
)
"""
