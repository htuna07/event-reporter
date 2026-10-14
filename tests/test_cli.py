import io
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from activity_reporter.cli import main
from activity_reporter.logging import configure_logging


class FailingSource:
    name = "broken"

    def fetch(self, start, end):
        raise RuntimeError("source unavailable")
        yield  # Makes this a generator so the failure occurs during ingestion.


class SuccessfulSource:
    name = "healthy"

    class Adapter:
        def adapt(self, payload):
            return payload

    adapter = Adapter()

    def __init__(self) -> None:
        self.fetch_called = False

    def fetch(self, start, end):
        self.fetch_called = True
        yield {"event": "kept"}


class FakeRepository:
    def __init__(self) -> None:
        self.upsert_calls = 0

    def create_schema(self) -> None:
        pass

    def upsert(self, events) -> int:
        self.upsert_calls += 1
        return len(events)


class CliTest(unittest.TestCase):
    def tearDown(self) -> None:
        configure_logging()

    def test_ingest_continues_with_later_sources_after_a_source_fails(self) -> None:
        start = datetime(2026, 9, 25, tzinfo=timezone.utc)
        end = datetime(2026, 9, 26, tzinfo=timezone.utc)
        settings = SimpleNamespace(start=start, end=end)
        repository = FakeRepository()
        healthy_source = SuccessfulSource()
        output = io.StringIO()

        with (
            patch("sys.argv", ["activity-reporter", "ingest"]),
            patch("activity_reporter.cli.environment", return_value={}),
            patch(
                "activity_reporter.cli.DatabaseSettings.from_environment",
                return_value=SimpleNamespace(url="sqlite://"),
            ),
            patch("activity_reporter.cli.build_repository", return_value=repository),
            patch(
                "activity_reporter.cli.IngestionSettings.from_environment",
                return_value=settings,
            ),
            patch(
                "activity_reporter.cli.discover_sources",
                return_value=[FailingSource(), healthy_source],
            ),
            redirect_stdout(output),
        ):
            result = main()

        self.assertEqual(result, 1)
        self.assertTrue(healthy_source.fetch_called)
        self.assertEqual(repository.upsert_calls, 1)
        self.assertIn("ingestion.source_failed", output.getvalue())
        self.assertIn("ingestion.source_completed", output.getvalue())


if __name__ == "__main__":
    unittest.main()
