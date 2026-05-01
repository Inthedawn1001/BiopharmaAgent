import unittest
from datetime import datetime, timezone

from biopharma_agent.contracts import RawDocument, SourceRef
from biopharma_agent.orchestration.postgres_source_state import PostgresSourceStateStore


class PostgresSourceStateTest(unittest.TestCase):
    def test_record_success_upserts_and_lists_state(self):
        source = SourceRef(
            name="fda_press_releases",
            kind="regulatory_feed",
            metadata={"collector": "feed", "category": "regulatory_press_release"},
        )
        store = FakePostgresSourceStateStore()

        record = store.record_success(
            source,
            started_at=_fixed_time(),
            completed_at=_fixed_time(),
            summary={"fetched": 2, "selected": 1, "analyzed": 1},
            documents=[RawDocument(source=source, document_id="doc-1")],
        )

        self.assertEqual(record["last_status"], "success")
        self.assertEqual(record["seen_document_ids"], ["doc-1"])
        self.assertEqual(store.seen_document_ids(source.name), {"doc-1"})
        executed_sql = "\n".join(sql for sql, _ in store.cursor.calls)
        self.assertIn("insert into source_states", executed_sql)

    def test_record_failure_preserves_seen_documents(self):
        source = SourceRef(name="sec_biopharma_filings", kind="market_regulatory_api")
        store = FakePostgresSourceStateStore()
        store.record_success(
            source,
            started_at=_fixed_time(),
            completed_at=_fixed_time(),
            summary={"selected": 1},
            documents=[RawDocument(source=source, document_id="sec-doc")],
        )

        record = store.record_failure(
            source,
            started_at=_fixed_time(),
            completed_at=_fixed_time(),
            error="rate limited",
        )

        self.assertEqual(record["last_status"], "failed")
        self.assertEqual(record["last_error"], "rate limited")
        self.assertEqual(record["seen_document_ids"], ["sec-doc"])
        self.assertEqual(record["consecutive_failures"], 1)


class FakePostgresSourceStateStore(PostgresSourceStateStore):
    def __init__(self):
        self.cursor = FakeSourceStateCursor()
        self.connection = FakeSourceStateConnection(self.cursor)
        self.dsn = "postgresql://example"
        self.connect_timeout = 10

    def _connect(self):
        return self.connection


class FakeSourceStateConnection:
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


class FakeSourceStateCursor:
    def __init__(self):
        self.calls = []
        self.rows = {}
        self.result = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split())
        self.calls.append((normalized, list(params or [])))
        if normalized.startswith("select source_name"):
            if "where source_name = %s" in normalized:
                row = self.rows.get(params[0])
                self.result = [row] if row else []
            else:
                self.result = [self.rows[key] for key in sorted(self.rows)]
            return
        if normalized.startswith("insert into source_states"):
            self.rows[params[0]] = (
                params[0],
                params[1],
                params[2],
                params[3],
                params[4],
                params[5],
                params[6],
                params[7],
                params[8],
                params[9],
                params[10],
                params[11],
                params[12],
                params[13],
                params[14],
                params[15],
                params[17],
            )
            self.result = []

    def fetchone(self):
        return self.result[0] if self.result else None

    def fetchall(self):
        return self.result


def _fixed_time():
    return datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc)


if __name__ == "__main__":
    unittest.main()
