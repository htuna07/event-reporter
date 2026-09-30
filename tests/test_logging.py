import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from activity_reporter.cli import build_parser
from activity_reporter.logging import configure_logging, get_logger


class LoggingTest(unittest.TestCase):
    def tearDown(self) -> None:
        configure_logging()

    def test_cli_logging_options_default_to_text_stdout_and_no_debug(self) -> None:
        arguments = build_parser().parse_args(["ingest"])

        self.assertFalse(arguments.debug)
        self.assertEqual(arguments.log_output, "stdout")
        self.assertEqual(arguments.log_format, "text")

    def test_cli_logging_options_accept_a_file_and_json_format(self) -> None:
        arguments = build_parser().parse_args(
            [
                "report",
                "--debug",
                "--log-output",
                "logs/activity.log",
                "--log-format",
                "json",
            ]
        )

        self.assertTrue(arguments.debug)
        self.assertEqual(arguments.log_output, "logs/activity.log")
        self.assertEqual(arguments.log_format, "json")

    def test_text_is_the_default_stdout_format(self) -> None:
        stream = io.StringIO()
        with patch("sys.stdout", stream):
            configure_logging()
            get_logger("test.logger").log(
                "event.completed", source="github", processed_events=2
            )

        entry = stream.getvalue().strip()
        self.assertIn(" INFO  test.logger event.completed", entry)
        self.assertIn("source=github", entry)
        self.assertIn("processed_events=2", entry)

    def test_json_and_text_expose_the_same_event_data(self) -> None:
        text_stream = io.StringIO()
        with patch("sys.stdout", text_stream):
            configure_logging()
            get_logger("test.logger").error(
                "event.failed", source="github", error_type="HTTPError"
            )

        json_stream = io.StringIO()
        with patch("sys.stdout", json_stream):
            configure_logging(log_format="json")
            get_logger("test.logger").error(
                "event.failed", source="github", error_type="HTTPError"
            )

        text_entry = text_stream.getvalue().strip()
        json_entry = json.loads(json_stream.getvalue())
        self.assertIn(" ERROR test.logger event.failed", text_entry)
        self.assertIn("source=github", text_entry)
        self.assertIn("error_type=HTTPError", text_entry)
        self.assertEqual(json_entry["level"], "ERROR")
        self.assertEqual(json_entry["logger"], "test.logger")
        self.assertEqual(json_entry["message"], "event.failed")
        self.assertEqual(json_entry["source"], "github")
        self.assertEqual(json_entry["error_type"], "HTTPError")
        self.assertTrue(json_entry["timestamp"].endswith("Z"))

    def test_debug_is_suppressed_unless_enabled(self) -> None:
        stream = io.StringIO()
        with patch("sys.stdout", stream):
            configure_logging()
            get_logger("test.logger").debug("event.diagnostic")
            configure_logging(debug=True)
            get_logger("test.logger").debug("event.diagnostic")

        self.assertEqual(stream.getvalue().count("event.diagnostic"), 1)
        self.assertIn(" DEBUG test.logger event.diagnostic", stream.getvalue())

    def test_file_sink_appends_json_lines_and_creates_parent_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "nested" / "activity.log"
            configure_logging(output=str(path), log_format="json")
            get_logger("test.logger").log("first.event", count=1)
            configure_logging(output=str(path), log_format="json")
            get_logger("test.logger").log("second.event", count=2)

            entries = [json.loads(line) for line in path.read_text().splitlines()]
            configure_logging()

        self.assertEqual([entry["message"] for entry in entries], ["first.event", "second.event"])
        self.assertEqual([entry["count"] for entry in entries], [1, 2])


if __name__ == "__main__":
    unittest.main()
