import unittest
from datetime import timezone
from pathlib import Path
from unittest.mock import patch

from activity_reporter.config import IngestionSettings, ReportSettings, environment


class SettingsTest(unittest.TestCase):
    @patch("activity_reporter.config.load_dotenv")
    def test_environment_loads_dotenv(self, load_dotenv) -> None:
        environment()

        load_dotenv.assert_called_once_with()

    def test_report_actors_are_exact_comma_separated_values(self) -> None:
        settings = ReportSettings.from_environment(
            {
                "REPORT_ACTORS": "htuna07, Tuna",
                "REPORT_START_TIME": "2026-09-25T00:00:00+03:00",
                "REPORT_END_TIME": "2026-09-26T00:00:00+03:00",
                "ANTHROPIC_API_KEY": "key",
                "ANTHROPIC_MODEL": "model",
            }
        )

        self.assertEqual(settings.actors, ("htuna07", "Tuna"))
        self.assertEqual(settings.start.tzinfo, timezone.utc)
        self.assertEqual(settings.max_events, 1_000)
        self.assertEqual(settings.max_input_characters, 200_000)
        self.assertEqual(
            settings.output_path,
            Path("output/reports/activity-report.md"),
        )

    def test_report_limits_must_be_positive_integers(self) -> None:
        values = {
            "REPORT_ACTORS": "actor",
            "REPORT_START_TIME": "2026-09-25T00:00:00Z",
            "REPORT_END_TIME": "2026-09-26T00:00:00Z",
            "ANTHROPIC_API_KEY": "key",
            "ANTHROPIC_MODEL": "model",
            "REPORT_MAX_EVENTS": "0",
        }

        with self.assertRaisesRegex(ValueError, "REPORT_MAX_EVENTS"):
            ReportSettings.from_environment(values)

    def test_ingestion_rejects_an_empty_range(self) -> None:
        with self.assertRaises(ValueError):
            IngestionSettings.from_environment(
                {
                    "INGEST_START_TIME": "2026-09-25T00:00:00Z",
                    "INGEST_END_TIME": "2026-09-25T00:00:00Z",
                }
            )


if __name__ == "__main__":
    unittest.main()
