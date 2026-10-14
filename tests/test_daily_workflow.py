import fcntl
import io
import json
import os
import subprocess
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.container_entrypoint import main as start_scheduler
from scripts.run_daily_workflow import (
    WorkflowFailure,
    main,
    run_stage,
    run_workflow,
    utc_window,
)


class DailyWorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.output = root / "output"
        self.runtime = root / "runtime"
        self.environment = {
            "TELEGRAM_BOT_TOKEN": "synthetic-token",
            "TELEGRAM_CHAT_ID": "synthetic-chat",
            "DATABASE_URL": "sqlite:///stale.db",
            "INGEST_START_TIME": "stale-date",
            "REPORT_END_TIME": "stale-date",
        }
        self.calls = []
        self.databases = []
        self.delivered_reports = []
        self.failing_stage = None
        self.failure_reason = "command exited with status 1"
        self.notification = Mock()
        self.notification.json.return_value = {"ok": True}
        self.post = self.enterContext(
            patch("scripts.run_daily_workflow.requests.post", return_value=self.notification)
        )
        self.enterContext(
            patch("scripts.run_daily_workflow.run_stage", side_effect=self.fake_stage)
        )
        self.enterContext(redirect_stdout(io.StringIO()))

    def fake_stage(self, stage, arguments, environment, deadline, **streams):
        self.calls.append((stage, dict(environment)))
        if stage == self.failing_stage:
            raise WorkflowFailure(stage, self.failure_reason)
        if stage == "ingestion":
            database = Path(environment["DATABASE_URL"].removeprefix("sqlite:///"))
            self.assertFalse(database.exists())
            database.write_text("synthetic database")
            self.databases.append(database)
        if stage == "report generation":
            streams["stdout"].write("Synthetic daily report\n")
            Path(environment["REPORT_OUTPUT_PATH"]).write_text("Synthetic daily report\n")
        if stage == "Telegram delivery":
            self.delivered_reports.append(streams["stdin"].read())

    def run_workflow(self):
        return run_workflow(self.environment, output=self.output, runtime=self.runtime)

    def test_success_and_each_invocation_refreshes_dates_and_database(self):
        first = datetime(2026, 10, 14, 14, 45, tzinfo=timezone.utc)
        with patch("scripts.run_daily_workflow.datetime") as clock:
            clock.now.return_value = first
            self.assertEqual(self.run_workflow(), 0)
            clock.now.return_value = first + timedelta(days=1)
            self.assertEqual(self.run_workflow(), 0)
        self.assertEqual(
            [stage for stage, _ in self.calls],
            ["ingestion", "report generation", "Telegram delivery"] * 2,
        )
        for stage, environment in self.calls:
            self.assertEqual(environment["INGEST_START_TIME"], environment["REPORT_START_TIME"])
            self.assertEqual(environment["INGEST_END_TIME"], environment["REPORT_END_TIME"])
            self.assertEqual(environment["REPORT_PROVIDER"], "openai")
            self.assertEqual(environment["OPENAI_MODEL"], "gpt-6-luna")
        self.assertEqual(self.calls[0][1]["INGEST_END_TIME"], "2026-10-14T14:45:00Z")
        self.assertEqual(self.calls[3][1]["INGEST_END_TIME"], "2026-10-15T14:45:00Z")
        self.assertEqual(len(set(self.databases)), 2)
        self.assertTrue(all(not database.exists() for database in self.databases))
        self.assertEqual(self.delivered_reports, ["Synthetic daily report\n"] * 2)
        self.assertTrue((self.output / "reports" / "activity-report.txt").exists())
        self.post.assert_not_called()
        self.assertEqual(self.environment["DATABASE_URL"], "sqlite:///stale.db")

    def test_stage_failures_stop_later_stages_and_notify(self):
        stages = ["ingestion", "report generation", "Telegram delivery"]
        for index, stage in enumerate(stages):
            with self.subTest(stage=stage):
                self.calls.clear()
                self.post.reset_mock()
                self.failing_stage = stage
                self.assertEqual(self.run_workflow(), 1)
                self.assertEqual(
                    [called for called, _ in self.calls], stages[:index + 1]
                )
                self.post.assert_called_once()
                message = self.post.call_args.kwargs["json"]["text"]
                self.assertIn(f"Stage: {stage}", message)
                self.assertNotIn("synthetic-token", message)
        self.assertEqual(self.delivered_reports, [])
        self.assertTrue(all(not database.exists() for database in self.databases))

    def test_timeout_notifies_and_does_not_send_report(self):
        self.failing_stage = "report generation"
        self.failure_reason = "30-minute workflow timeout"
        self.assertEqual(self.run_workflow(), 1)
        self.assertIn("30-minute workflow timeout", self.post.call_args.kwargs["json"]["text"])
        self.assertEqual(self.delivered_reports, [])

    def test_failed_notification_preserves_failure_status(self):
        self.failing_stage = "ingestion"
        self.notification.json.return_value = {"ok": False}
        self.assertEqual(self.run_workflow(), 1)
        self.post.side_effect = ValueError("synthetic failure")
        self.assertEqual(self.run_workflow(), 1)

    def test_overlapping_invocation_skips_all_commands(self):
        self.runtime.mkdir()
        with (self.runtime / "workflow.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual(self.run_workflow(), 0)
        self.assertEqual(self.calls, [])
        self.post.assert_not_called()

    def test_missing_telegram_configuration_fails_before_ingestion(self):
        self.environment.pop("TELEGRAM_BOT_TOKEN")
        self.assertEqual(self.run_workflow(), 1)
        self.assertEqual(self.calls, [])
        self.post.assert_not_called()

    def test_explicit_provider_and_model_are_preserved(self):
        self.environment.update(REPORT_PROVIDER="anthropic", ANTHROPIC_MODEL="synthetic-model")
        self.assertEqual(self.run_workflow(), 0)
        self.assertEqual(self.calls[1][1]["REPORT_PROVIDER"], "anthropic")
        self.assertEqual(self.calls[1][1]["ANTHROPIC_MODEL"], "synthetic-model")

    def test_cron_loads_the_saved_environment_instead_of_its_own(self):
        snapshot = Path(self.temporary.name) / "synthetic-environment.json"
        values = dict(self.environment, REPORT_ACTORS="actor with spaces and 'quotes'")
        snapshot.write_text(json.dumps(values))
        with (
            patch("sys.argv", ["runner", "--environment", str(snapshot)]),
            patch("scripts.run_daily_workflow.run_workflow", return_value=0) as run,
        ):
            self.assertEqual(main(), 0)
        run.assert_called_once_with(values)

    def test_entrypoint_saves_a_restricted_environment_for_cron(self):
        with (
            patch("scripts.container_entrypoint.Path", return_value=self.runtime),
            patch.dict(os.environ, self.environment, clear=True),
            patch("scripts.container_entrypoint.os.execv") as execute,
        ):
            start_scheduler()
        snapshot = self.runtime / "environment.json"
        self.assertEqual(self.runtime.stat().st_mode & 0o777, 0o700)
        self.assertEqual(snapshot.stat().st_mode & 0o777, 0o600)
        self.assertEqual(json.loads(snapshot.read_text()), self.environment)
        execute.assert_called_once_with("/usr/sbin/cron", ["cron", "-f"])


class WorkflowStageTest(unittest.TestCase):
    def test_timeout_terminates_the_real_subprocess(self):
        start = time.monotonic()
        with self.assertRaisesRegex(WorkflowFailure, "30-minute workflow timeout"):
            run_stage(
                "synthetic long-running command",
                ["timeit", "-n", "1", "-r", "1", "__import__('time').sleep(30)"],
                {},
                start + 0.2,
                stdout=subprocess.DEVNULL,
            )
        self.assertLess(time.monotonic() - start, 5)

    def test_nonzero_subprocess_status_is_a_failure(self):
        with self.assertRaisesRegex(WorkflowFailure, "command exited with status 7"):
            run_stage(
                "synthetic failed command",
                ["timeit", "-n", "1", "-r", "1", "__import__('os')._exit(7)"],
                {}, time.monotonic() + 5, stdout=subprocess.DEVNULL,
            )

    def test_window_crosses_local_midnight_and_year_boundary(self):
        now = datetime(2027, 1, 1, 0, 5, 0, 123, tzinfo=timezone(timedelta(hours=3)))
        window = utc_window(now)
        self.assertEqual(window["INGEST_START_TIME"], "2026-12-30T21:05:00Z")
        self.assertEqual(window["REPORT_END_TIME"], "2026-12-31T21:05:00Z")


if __name__ == "__main__":
    unittest.main()
