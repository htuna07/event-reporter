import tempfile
import unittest
from pathlib import Path

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from activity_reporter.database import EventRow, build_repository


class DatabaseSchemaTest(unittest.TestCase):
    def test_uses_internal_identity_and_source_external_id_uniqueness(self) -> None:
        definition = str(
            CreateTable(EventRow.__table__).compile(dialect=postgresql.dialect())
        )

        self.assertIn("id BIGINT GENERATED ALWAYS AS IDENTITY", definition)
        self.assertIn("PRIMARY KEY (id)", definition)
        self.assertIn(
            "CONSTRAINT uq_events_source_external_id UNIQUE (source, external_id)",
            definition,
        )

    def test_sqlite_waits_for_a_concurrent_writer(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = build_repository(f"sqlite:///{Path(directory) / 'events.db'}")
            self.addCleanup(repository.engine.dispose)
            with repository.engine.connect() as connection:
                timeout = connection.exec_driver_sql("PRAGMA busy_timeout").scalar()

        self.assertEqual(timeout, 30_000)


if __name__ == "__main__":
    unittest.main()
