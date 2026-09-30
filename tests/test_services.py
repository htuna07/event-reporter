import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from activity_reporter.domain import NormalizedEvent, StoredEvent
from activity_reporter.ingestion import IngestionService
from activity_reporter.reporting import ReportService
from activity_reporter.reporters.anthropic import AnthropicReportGenerator
from activity_reporter.reporters.base import ReportGenerationParameters
from activity_reporter.reporters.factory import build_report_generator
from activity_reporter.reporters.openai import OpenAIReportGenerator

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
    def report_parameters(self, **overrides) -> ReportGenerationParameters:
        return ReportGenerationParameters(
            model="model",
            max_events=overrides.get("max_events", 10),
            max_input_characters=overrides.get("max_input_characters", 10_000),
            max_tokens=1_500,
        )

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
            parameters=self.report_parameters(max_events=1),
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
            parameters=self.report_parameters(max_input_characters=10),
        )

        with self.assertRaisesRegex(ValueError, "REPORT_MAX_INPUT_CHARACTERS"):
            generator.generate(
                [stored_event()],
                ("actor",),
                START,
                END,
            )

    @patch("activity_reporter.reporters.openai.OpenAI")
    def test_openai_generator_uses_common_request_parameters(self, openai) -> None:
        client = openai.return_value
        client.responses.create.return_value = SimpleNamespace(output_text="report")
        generator = OpenAIReportGenerator("key", self.report_parameters())

        result = generator.generate([stored_event()], ("actor",), START, END)

        self.assertEqual(result, "report")
        openai.assert_called_once_with(api_key="key")
        arguments = client.responses.create.call_args.kwargs
        self.assertEqual(arguments["model"], "model")
        self.assertEqual(arguments["max_output_tokens"], 1_500)
        self.assertIn("normalized event logs", arguments["instructions"])
        self.assertIn('"actors": ["actor"]', arguments["input"])

    @patch("activity_reporter.reporters.openai.OpenAI")
    @patch("activity_reporter.reporters.anthropic.Anthropic")
    def test_factory_selects_configured_provider(self, anthropic, openai) -> None:
        common = {
            "api_key": "key",
            "model": "model",
            "max_events": 10,
            "max_input_characters": 10_000,
            "max_tokens": 1_500,
        }

        anthropic_generator = build_report_generator(
            SimpleNamespace(provider="anthropic", **common)
        )
        openai_generator = build_report_generator(
            SimpleNamespace(provider="openai", **common)
        )

        self.assertIsInstance(anthropic_generator, AnthropicReportGenerator)
        self.assertIsInstance(openai_generator, OpenAIReportGenerator)
        anthropic.assert_called_once_with(api_key="key")
        openai.assert_called_once_with(api_key="key")


if __name__ == "__main__":
    unittest.main()
