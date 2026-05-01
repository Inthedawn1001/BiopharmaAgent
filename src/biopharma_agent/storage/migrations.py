"""PostgreSQL schema migration runner."""

from __future__ import annotations

import hashlib
import importlib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DEFAULT_SCHEMA_PATH = Path("infra/postgres/schema.sql")
DEFAULT_MIGRATION_ID = "0001_initial_schema"
DEFAULT_MIGRATIONS_DIR = Path("infra/postgres/migrations")


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
        results = self.migrate_all()
        return results[0]

    def migrate_all(self) -> list[MigrationResult]:
        migrations = [
            (
                self.migration_id,
                self.schema_path,
                self.schema_path.read_text(encoding="utf-8"),
            )
        ]
        if self.schema_path == DEFAULT_SCHEMA_PATH and DEFAULT_MIGRATIONS_DIR.exists():
            for path in sorted(DEFAULT_MIGRATIONS_DIR.glob("*.sql")):
                migrations.append((path.stem, path, path.read_text(encoding="utf-8")))
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(_MIGRATION_TABLE_SQL)
                results: list[MigrationResult] = []
                for migration_id, path, sql in migrations:
                    checksum = hashlib.sha256(sql.encode("utf-8")).hexdigest()
                    cursor.execute(
                        "select checksum from schema_migrations where migration_id = %s",
                        (migration_id,),
                    )
                    row = cursor.fetchone()
                    if row:
                        existing_checksum = row[0]
                        if existing_checksum != checksum:
                            if migration_id == self.migration_id:
                                legacy_sql = _legacy_safe_initial_schema(sql)
                                legacy_checksum = hashlib.sha256(legacy_sql.encode("utf-8")).hexdigest()
                                if legacy_checksum != existing_checksum:
                                    raise ValueError(
                                        "PostgreSQL migration checksum mismatch for "
                                        f"{migration_id}: expected {existing_checksum}, got {checksum}"
                                    )
                                checksum = existing_checksum
                            else:
                                raise ValueError(
                                    "PostgreSQL migration checksum mismatch for "
                                    f"{migration_id}: expected {existing_checksum}, got {checksum}"
                                )
                        results.append(
                            MigrationResult(
                                migration_id=migration_id,
                                status="skipped",
                                checksum=checksum,
                                schema_path=str(path),
                            )
                        )
                        continue

                    cursor.execute(sql)
                    cursor.execute(
                        """
                        insert into schema_migrations (migration_id, checksum)
                        values (%s, %s)
                        """,
                        (migration_id, checksum),
                    )
                    results.append(
                        MigrationResult(
                            migration_id=migration_id,
                            status="applied",
                            checksum=checksum,
                            schema_path=str(path),
                        )
                    )
            connection.commit()
        return results

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


def _legacy_safe_initial_schema(sql: str) -> str:
    marker = "create table if not exists source_states"
    if marker not in sql:
        return sql
    return sql.split(marker, 1)[0].rstrip() + "\n"
