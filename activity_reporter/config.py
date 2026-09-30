import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv


def parse_datetime(value: str, name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{name} must be an ISO 8601 timestamp.") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{name} must include a timezone.")
    return parsed.astimezone(timezone.utc)


def require(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name)
    if not value:
        raise ValueError(f"{name} must be set.")
    return value


def comma_separated(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())


def positive_integer(
    environment: Mapping[str, str],
    name: str,
    default: int,
) -> int:
    value = environment.get(name, str(default))
    try:
        parsed = int(value)
    except ValueError as error:
        raise ValueError(f"{name} must be an integer.") from error
    if parsed <= 0:
        raise ValueError(f"{name} must be greater than zero.")
    return parsed


@dataclass(frozen=True, slots=True)
class DatabaseSettings:
    url: str

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> "DatabaseSettings":
        return cls(url=require(environment, "DATABASE_URL"))


@dataclass(frozen=True, slots=True)
class IngestionSettings:
    start: datetime
    end: datetime

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> "IngestionSettings":
        settings = cls(
            start=parse_datetime(
                require(environment, "INGEST_START_TIME"), "INGEST_START_TIME"
            ),
            end=parse_datetime(
                require(environment, "INGEST_END_TIME"), "INGEST_END_TIME"
            ),
        )
        if settings.start >= settings.end:
            raise ValueError(
                "INGEST_START_TIME must be before INGEST_END_TIME.")
        return settings


@dataclass(frozen=True, slots=True)
class ReportSettings:
    actors: tuple[str, ...]
    start: datetime
    end: datetime
    anthropic_api_key: str
    anthropic_model: str
    max_events: int
    max_input_characters: int
    max_tokens: int
    output_path: Path

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> "ReportSettings":
        actors = comma_separated(require(environment, "REPORT_ACTORS"))
        if not actors:
            raise ValueError("REPORT_ACTORS must contain at least one actor.")
        output = environment.get(
            "REPORT_OUTPUT_PATH",
            "output/reports/activity-report.md",
        )
        settings = cls(
            actors=actors,
            start=parse_datetime(
                require(environment, "REPORT_START_TIME"), "REPORT_START_TIME"
            ),
            end=parse_datetime(
                require(environment, "REPORT_END_TIME"), "REPORT_END_TIME"
            ),
            anthropic_api_key=require(environment, "ANTHROPIC_API_KEY"),
            anthropic_model=require(environment, "ANTHROPIC_MODEL"),
            max_events=positive_integer(
                environment,
                "REPORT_MAX_EVENTS",
                1_000,
            ),
            max_input_characters=positive_integer(
                environment,
                "REPORT_MAX_INPUT_CHARACTERS",
                200_000,
            ),
            max_tokens=positive_integer(
                environment,
                "REPORT_MAX_TOKENS",
                1500,
            ),
            output_path=Path(output),
        )
        if settings.start >= settings.end:
            raise ValueError(
                "REPORT_START_TIME must be before REPORT_END_TIME.")
        return settings


def environment() -> Mapping[str, str]:
    load_dotenv()
    return os.environ
