import unittest
from datetime import datetime, timezone

from activity_reporter.domain import NormalizedEvent, StoredEvent
from activity_reporter.ingestion import IngestionService
from activity_reporter.reporting import AnthropicReportGenerator, ReportService

START = datetime(2026, 9, 25, tzinfo=timezone.utc)
END = datetime(2026, 9, 26, tzinfo=timezone.utc)


def normalized_event(identifier: str = "1") -> NormalizedEvent:
    return NormalizedEvent(
        external_id=identifier,
        source="test",
        timestamp=START,
        actor="actor",
        action="action",
        resource="resource",
        raw_payload={"id": identifier},
    )


def stored_event(identifier: str = "1") -> StoredEvent:
    return StoredEvent(
        id=int(identifier),
        external_id=identifier,
        source="test",
        timestamp=START,
        actor="actor",
        action="action",
        resource="resource",
        raw_payload={"id": identifier},
    )


class FakeAdapter:
    def adapt(self, payload: dict) -> NormalizedEvent:
        return normalized_event(payload["id"])


class FakeSource:
    name = "test"
    adapter = FakeAdapter()

    def fetch(self, start: datetime, end: datetime):
        yield {"id": "1"}
        yield {"id": "2"}
        yield {"id": "3"}


class FakeRepository:
    def __init__(self) -> None:
        self.batches: list[list[NormalizedEvent]] = []
        self.find_arguments = None

    def upsert(self, events: list[NormalizedEvent]) -> int:
        self.batches.append(list(events))
        return len(events)

    def find(self, actors, start, end):
        self.find_arguments = (actors, start, end)
        return [stored_event()]


class FakeGenerator:
    def __init__(self) -> None:
        self.arguments = None

    def generate(self, events, actors, start, end) -> str:
        self.arguments = (events, actors, start, end)
        return "report"


class ServiceTest(unittest.TestCase):
    def test_ingestion_adapts_and_writes_batches(self) -> None:
        repository = FakeRepository()

        count = IngestionService(repository, batch_size=2).ingest(
            FakeSource(), START, END
        )

        self.assertEqual(count, 3)
        self.assertEqual(
            [[item.external_id for item in batch] for batch in repository.batches],
            [["1", "2"], ["3"]],
        )

    def test_reporting_passes_exact_actor_list_and_range(self) -> None:
        repository = FakeRepository()
        generator = FakeGenerator()

        result = ReportService(repository, generator).create(
            ("github-user", "aws-user"), START, END
        )

        self.assertEqual(result, "report")
        self.assertEqual(
            repository.find_arguments,
            (("github-user", "aws-user"), START, END),
        )
        self.assertEqual(
            generator.arguments[1:],
            (("github-user", "aws-user"), START, END),
        )

    def test_anthropic_generator_rejects_too_many_events(self) -> None:
        generator = AnthropicReportGenerator(
            api_key="key",
            model="model",
            max_events=1,
            max_input_characters=10_000,
            max_tokens=1_500,
        )

        with self.assertRaisesRegex(ValueError, "REPORT_MAX_EVENTS"):
            generator.generate(
                [stored_event("1"), stored_event("2")],
                ("actor",),
                START,
                END,
            )

    def test_anthropic_generator_rejects_oversized_input(self) -> None:
        generator = AnthropicReportGenerator(
            api_key="key",
            model="model",
            max_events=10,
            max_input_characters=10,
            max_tokens=1_500,
        )

        with self.assertRaisesRegex(ValueError, "REPORT_MAX_INPUT_CHARACTERS"):
            generator.generate(
                [stored_event()],
                ("actor",),
                START,
                END,
            )


if __name__ == "__main__":
    unittest.main()
