import unittest

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from activity_reporter.database import EventRow


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


if __name__ == "__main__":
    unittest.main()
