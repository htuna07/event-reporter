"""Run the local scheduled workflows: hourly ingestion and the daily report."""

import argparse
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
from zoneinfo import ZoneInfo

import requests

WORKFLOW_TIMEOUT_SECONDS = 30 * 60
TIMEZONE = ZoneInfo("Europe/Istanbul")
INGEST_LOOKBACK = timedelta(hours=2)
INGEST_FAILURE_THRESHOLD = 3
MODES = ("ingest", "report")
PARTIAL_INGESTION_STATUS = 2
SOURCE_NAMES = {"github": "GitHub", "aws_cloudtrail": "AWS CloudTrail"}


class WorkflowFailure(Exception):
    def __init__(self, stage: str, reason: str) -> None:
        self.stage = stage
        self.reason = reason
        super().__init__(f"{stage}: {reason}")


def _utc_text(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def time_window(mode: str, now: datetime) -> dict[str, str]:
    """Return the UTC time window for a workflow mode.

    `ingest` re-reads the last two hours; overlapping windows are safe because
    ingestion is idempotent, and they absorb delayed source events. `report`
    covers the current calendar day in Europe/Istanbul, from local midnight
    until now.
    """
    end = now.astimezone(timezone.utc).replace(microsecond=0)
    if mode == "ingest":
        start = end - INGEST_LOOKBACK
    else:
        local_midnight = end.astimezone(TIMEZONE).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        start = local_midnight.astimezone(timezone.utc)
    names = ("INGEST",) if mode == "ingest" else ("INGEST", "REPORT")
    return {
        f"{name}_{boundary}_TIME": _utc_text(value)
        for name in names
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
    ok_statuses: tuple[int, ...] = (0,),
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
    if status not in ok_statuses:
        raise WorkflowFailure(stage, f"command exited with status {status}")


def read_ingest_failures(path: Path) -> dict[str, list[str]] | None:
    """Return failed sources and their failures, or None if unreadable."""
    try:
        data = json.loads(path.read_text())
        failures = data["failures"]
        if not isinstance(failures, dict) or not all(
            isinstance(items, list) for items in failures.values()
        ):
            return None
        return {str(source): [str(item) for item in items] for source, items in failures.items()}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def data_notice(failures: dict[str, list[str]] | None) -> str:
    """Describe incomplete data in plain text for the end of a report."""
    if failures is None:
        return (
            "\n\nData notice\n"
            "• The ingestion status could not be read.\n"
            "This report may be missing recent activity."
        )
    if not failures:
        return ""
    lines = ["", "", "Data notice"]
    for source, items in failures.items():
        name = SOURCE_NAMES.get(source, source)
        detail = f" for: {', '.join(items)}" if items else ""
        lines.append(f"• {name} could not be refreshed{detail}.")
    lines.append(
        "Events newer than the last successful sync from these sources "
        "may be missing from this report."
    )
    return "\n".join(lines)


def send_notification(environment: Mapping[str, str], text: str) -> bool:
    token = environment.get("TELEGRAM_BOT_TOKEN")
    chat = environment.get("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return False
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat, "text": text},
            timeout=30,
        )
        response.raise_for_status()
        result = response.json()
        return isinstance(result, dict) and result.get("ok") is True
    except (requests.RequestException, ValueError):
        return False


def notify_failure(
    environment: Mapping[str, str], failure: WorkflowFailure, run_time: datetime
) -> bool:
    return send_notification(
        environment,
        "Daily Activity Report failed (local Docker workflow).\n"
        f"Run: {run_time.isoformat(timespec='seconds')}\n"
        f"Stage: {failure.stage}\n"
        f"Reason: {failure.reason}\n"
        "See Docker logs and output/logs for details.",
    )


def notify_ingest_failures(
    environment: Mapping[str, str],
    failure: WorkflowFailure,
    run_time: datetime,
    count: int,
) -> bool:
    return send_notification(
        environment,
        f"Hourly ingestion has failed {count} times in a row "
        "(local Docker workflow).\n"
        f"Latest run: {run_time.isoformat(timespec='seconds')}\n"
        f"Reason: {failure.reason}\n"
        "See Docker logs and output/logs for details.",
    )


def record_ingest_result(output: Path, succeeded: bool) -> int:
    """Track consecutive ingestion failures; returns the current streak."""
    path = output / "state" / "ingest-failures"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        previous = int(path.read_text().strip() or 0) if path.exists() else 0
        streak = 0 if succeeded else previous + 1
        path.write_text(str(streak))
        return streak
    except (OSError, ValueError):
        return 0


def run_workflow(
    environment: Mapping[str, str],
    *,
    mode: str = "report",
    output: Path = Path("output"),
) -> int:
    if mode not in MODES:
        raise ValueError(f"mode must be one of: {', '.join(MODES)}")
    values = dict(environment)
    now = datetime.now(timezone.utc)
    deadline = time.monotonic() + WORKFLOW_TIMEOUT_SECONDS
    stage = "setup"
    try:
        (output / "logs").mkdir(parents=True, exist_ok=True)
        (output / "reports").mkdir(parents=True, exist_ok=True)
        (output / "data").mkdir(parents=True, exist_ok=True)
        values.update(time_window(mode, now))
        values["REPORT_OUTPUT_PATH"] = str(
            output / "reports" / "activity-report.txt"
        )
        values["DATABASE_URL"] = (
            f"sqlite:///{output / 'data' / 'activity-reporter.db'}"
        )
        log(
            f"{'Daily workflow' if mode == 'report' else 'Hourly ingestion'} "
            f"started: {values['INGEST_START_TIME']} to {values['INGEST_END_TIME']}",
            output,
        )
        try:
            if mode == "report" and (
                not values.get("TELEGRAM_BOT_TOKEN")
                or not values.get("TELEGRAM_CHAT_ID")
            ):
                raise WorkflowFailure(
                    "configuration", "Telegram token and chat ID are required"
                )
            application_log = str(output / "logs" / "activity-reporter.txt")
            status_path = output / "state" / "ingest-status.json"
            status_path.unlink(missing_ok=True)
            stage = "ingestion"
            run_stage(
                stage,
                [
                    "activity_reporter",
                    "ingest",
                    "--log-output",
                    application_log,
                    "--failures-output",
                    str(status_path),
                ],
                values,
                deadline,
                # A report still goes out when some sources failed; it says so.
                ok_statuses=(
                    (0, PARTIAL_INGESTION_STATUS) if mode == "report" else (0,)
                ),
            )
            log("Ingestion completed.", output)
            if mode == "ingest":
                record_ingest_result(output, succeeded=True)
                return 0
            stage = "report generation"
            with tempfile.TemporaryFile("w+") as report:
                run_stage(
                    stage,
                    ["activity_reporter", "report", "--log-output", application_log],
                    values,
                    deadline,
                    stdout=report,
                )
                notice = data_notice(read_ingest_failures(status_path))
                if notice:
                    log("Report is incomplete; appending a data notice.", output)
                    report.seek(0, os.SEEK_END)
                    report.write(notice)
                    report.flush()
                    with Path(values["REPORT_OUTPUT_PATH"]).open("a") as saved:
                        saved.write(notice)
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
            label = "Daily workflow" if mode == "report" else "Hourly ingestion"
            log(f"{label} failed: {failure}", output)
            if mode == "ingest":
                streak = record_ingest_result(output, succeeded=False)
                if streak == INGEST_FAILURE_THRESHOLD:
                    delivered = notify_ingest_failures(
                        values, failure, now, streak
                    )
                    log(
                        "Failure notification sent."
                        if delivered
                        else "Failure notification could not be sent.",
                        output,
                    )
                return 1
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
        log(f"Workflow failed: {failure}", output)
        if mode == "report" and not notify_failure(values, failure, now):
            log("Failure notification could not be sent.", output)
        return 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--environment", type=Path,
        help="runtime environment snapshot supplied by cron",
    )
    parser.add_argument(
        "--mode", choices=MODES, default="report",
        help="ingest: store recent events; report: ingest the day, report, and send",
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
    return run_workflow(values, mode=arguments.mode)


if __name__ == "__main__":
    raise SystemExit(main())
