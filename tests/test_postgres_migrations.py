import tempfile
import unittest
from pathlib import Path

from biopharma_agent.storage.migrations import PostgresMigrationRunner


class PostgresMigrationRunnerTest(unittest.TestCase):
    def test_migration_applies_schema_and_records_checksum(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            schema_path = Path(temp_dir) / "schema.sql"
            schema_path.write_text("create table if not exists example(id int);", encoding="utf-8")
            runner = FakeMigrationRunner("postgresql://example", schema_path=schema_path)

            result = runner.migrate()

            self.assertEqual(result.status, "applied")
            executed_sql = "\n".join(call[0] for call in runner.cursor.calls)
            self.assertIn("create table if not exists schema_migrations", executed_sql)
            self.assertIn("create table if not exists example", executed_sql)
            self.assertEqual(runner.cursor.recorded_checksum, result.checksum)

    def test_migration_skips_when_checksum_matches(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            schema_path = Path(temp_dir) / "schema.sql"
            schema_path.write_text("create table if not exists example(id int);", encoding="utf-8")
            first = FakeMigrationRunner("postgresql://example", schema_path=schema_path)
            applied = first.migrate()

            second = FakeMigrationRunner(
                "postgresql://example",
                schema_path=schema_path,
                existing_checksum=applied.checksum,
            )
            result = second.migrate()

            self.assertEqual(result.status, "skipped")
            executed_sql = "\n".join(call[0] for call in second.cursor.calls)
            self.assertNotIn("create table if not exists example", executed_sql)

    def test_migration_rejects_checksum_mismatch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            schema_path = Path(temp_dir) / "schema.sql"
            schema_path.write_text("create table if not exists example(id int);", encoding="utf-8")
            runner = FakeMigrationRunner(
                "postgresql://example",
                schema_path=schema_path,
                existing_checksum="old-checksum",
            )

            with self.assertRaises(ValueError):
                runner.migrate()

    def test_migrate_all_applies_default_incremental_migrations(self):
        runner = FakeMigrationRunner("postgresql://example")

        results = runner.migrate_all()

        self.assertGreaterEqual(len(results), 2)
        self.assertEqual(results[0].migration_id, "0001_initial_schema")
        self.assertIn("0002_source_states", {result.migration_id for result in results})
        executed_sql = "\n".join(call[0] for call in runner.cursor.calls)
        self.assertIn("create table if not exists source_states", executed_sql)


class FakeMigrationRunner(PostgresMigrationRunner):
    def __init__(self, *args, existing_checksum=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.cursor = FakeMigrationCursor(existing_checksum)
        self.connection = FakeMigrationConnection(self.cursor)

    def _connect(self):
        return self.connection


class FakeMigrationConnection:
    def __init__(self, cursor):
        self.cursor_instance = cursor
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.commits += 1


class FakeMigrationCursor:
    def __init__(self, existing_checksum):
        self.calls = []
        self.result = None
        self.recorded_checksum = None
        self.existing_checksums = (
            existing_checksum if isinstance(existing_checksum, dict) else {"0001_initial_schema": existing_checksum}
        )

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split())
        self.calls.append((normalized, list(params or [])))
        if normalized.startswith("select checksum from schema_migrations"):
            checksum = self.existing_checksums.get(params[0])
            self.result = (checksum,) if checksum else None
            return
        if normalized.startswith("insert into schema_migrations"):
            self.recorded_checksum = params[1]
            self.existing_checksums[params[0]] = params[1]
        self.result = None

    def fetchone(self):
        return self.result


if __name__ == "__main__":
    unittest.main()
