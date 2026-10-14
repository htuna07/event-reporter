"""Run the daily local equivalent of the GitHub Actions job."""

import argparse
import fcntl
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import IO, Mapping

import requests

WORKFLOW_TIMEOUT_SECONDS = 30 * 60


class WorkflowFailure(Exception):
    def __init__(self, stage: str, reason: str) -> None:
        self.stage = stage
        self.reason = reason
        super().__init__(f"{stage}: {reason}")


def utc_window(now: datetime) -> dict[str, str]:
    end = now.astimezone(timezone.utc).replace(microsecond=0)
    start = end - timedelta(days=1)
    return {
        f"{command}_{boundary}_TIME": value.isoformat().replace("+00:00", "Z")
        for command in ("INGEST", "REPORT")
        for boundary, value in (("START", start), ("END", end))
    }


def log(message: str, output: Path) -> None:
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    line = f"{timestamp} {message}"
    print(line, flush=True)
    try:
        with (output / "logs" / "daily-workflow.log").open("a") as stream:
            stream.write(line + "\n")
    except OSError:
        print("Workflow log could not be written.", file=sys.stderr, flush=True)


def run_stage(
    stage: str,
    arguments: list[str],
    environment: Mapping[str, str],
    deadline: float,
    *,
    stdin: IO | None = None,
    stdout: IO | None = None,
) -> None:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise WorkflowFailure(stage, "30-minute workflow timeout")
    try:
        with subprocess.Popen(
            [sys.executable, "-m", *arguments],
            env=dict(environment),
            stdin=stdin,
            stdout=stdout,
            start_new_session=True,
        ) as process:
            try:
                status = process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise WorkflowFailure(stage, "30-minute workflow timeout") from None
    except OSError:
        raise WorkflowFailure(stage, "command could not be started") from None
    if status != 0:
        raise WorkflowFailure(stage, f"command exited with status {status}")


def notify_failure(
    environment: Mapping[str, str], failure: WorkflowFailure, run_time: datetime
) -> bool:
    token = environment.get("TELEGRAM_BOT_TOKEN")
    chat = environment.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return False
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": chat,
                "text": (
                    "Daily Activity Report failed (local Docker workflow).\n"
                    f"Run: {run_time.isoformat(timespec='seconds')}\n"
                    f"Stage: {failure.stage}\n"
                    f"Reason: {failure.reason}\n"
                    "See Docker logs and output/logs for details."
                ),
            },
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()
        return isinstance(result, dict) and result.get("ok") is True
    except (requests.RequestException, ValueError):
        return False


def run_workflow(
    environment: Mapping[str, str],
    *,
    output: Path = Path("output"),
    runtime: Path = Path("/run/activity-reporter"),
) -> int:
    values = dict(environment)
    now = datetime.now(timezone.utc)
    deadline = time.monotonic() + WORKFLOW_TIMEOUT_SECONDS
    stage = "setup"
    try:
        runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
        with (runtime / "workflow.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                print("Daily workflow already running; skipping this invocation.", flush=True)
                return 0

            (output / "logs").mkdir(parents=True, exist_ok=True)
            (output / "reports").mkdir(parents=True, exist_ok=True)
            values.update(utc_window(now))
            values["REPORT_PROVIDER"] = values.get("REPORT_PROVIDER") or "openai"
            values["OPENAI_MODEL"] = values.get("OPENAI_MODEL") or "gpt-6-luna"
            values["REPORT_OUTPUT_PATH"] = str(
                output / "reports" / "activity-report.txt"
            )
            log(
                f"Daily workflow started: {values['INGEST_START_TIME']} to "
                f"{values['INGEST_END_TIME']}",
                output,
            )
            try:
                if not values.get("TELEGRAM_BOT_TOKEN") or not values.get(
                    "TELEGRAM_CHAT_ID"
                ):
                    raise WorkflowFailure(
                        "configuration", "Telegram token and chat ID are required"
                    )
                with tempfile.TemporaryDirectory(
                    prefix="activity-reporter-"
                ) as temporary:
                    work = Path(temporary)
                    values["DATABASE_URL"] = f"sqlite:///{work / 'activity-reporter.db'}"
                    application_log = str(output / "logs" / "activity-reporter.txt")
                    stage = "ingestion"
                    run_stage(
                        stage,
                        ["activity_reporter", "ingest", "--log-output", application_log],
                        values,
                        deadline,
                    )
                    log("Ingestion completed.", output)
                    stage = "report generation"
                    with (work / "report.txt").open("w+") as report:
                        run_stage(
                            stage,
                            ["activity_reporter", "report", "--log-output", application_log],
                            values,
                            deadline,
                            stdout=report,
                        )
                        report.seek(0)
                        stage = "Telegram delivery"
                        run_stage(
                            stage,
                            ["scripts.send_telegram_report"],
                            values,
                            deadline,
                            stdin=report,
                        )
                log("Daily workflow completed; report delivered to Telegram.", output)
                return 0
            except WorkflowFailure as failure:
                log(f"Daily workflow failed: {failure}", output)
                delivered = notify_failure(values, failure, now)
                log(
                    "Failure notification sent."
                    if delivered
                    else "Failure notification could not be sent.",
                    output,
                )
                return 1
    except OSError:
        failure = WorkflowFailure(stage, "local file or directory could not be accessed")
        log(f"Daily workflow failed: {failure}", output)
        if not notify_failure(values, failure, now):
            log("Failure notification could not be sent.", output)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--environment", type=Path,
        help="runtime environment snapshot supplied by cron",
    )
    arguments = parser.parse_args()
    values = dict(os.environ)
    if arguments.environment is not None:
        try:
            values = json.loads(arguments.environment.read_text())
            if not isinstance(values, dict) or not all(
                isinstance(key, str) and isinstance(value, str)
                for key, value in values.items()
            ):
                raise ValueError("Invalid runtime environment")
        except (OSError, ValueError):
            print("Runtime environment could not be loaded.", file=sys.stderr)
            return 1
    return run_workflow(values)


if __name__ == "__main__":
    raise SystemExit(main())
