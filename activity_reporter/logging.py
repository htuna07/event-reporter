"""Small structured application logger with interchangeable output strategies."""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol, TextIO


@dataclass(frozen=True, slots=True)
class LogEvent:
    timestamp: datetime
    level: str
    logger: str
    message: str
    context: dict[str, Any]


class LogFormatter(Protocol):
    def format(self, event: LogEvent) -> str: ...


class LogSink(Protocol):
    def write(self, entry: str) -> None: ...


class TextLogFormatter:
    def format(self, event: LogEvent) -> str:
        timestamp = _timestamp(event.timestamp)
        fields = " ".join(
            f"{key}={_text_value(value)}" for key, value in event.context.items()
        )
        suffix = f" {fields}" if fields else ""
        return (
            f"{timestamp} {event.level:<5} {event.logger} "
            f"{event.message}{suffix}"
        )


class JsonLogFormatter:
    def format(self, event: LogEvent) -> str:
        return json.dumps(
            {
                "timestamp": _timestamp(event.timestamp),
                "level": event.level,
                "logger": event.logger,
                "message": event.message,
                **event.context,
            },
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
        )


class StdoutLogSink:
    def __init__(self, stream: TextIO | None = None) -> None:
        self.stream = stream or sys.stdout

    def write(self, entry: str) -> None:
        print(entry, file=self.stream, flush=True)


class FileLogSink:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.stream = path.open("a", encoding="utf-8", buffering=1)

    def write(self, entry: str) -> None:
        self.stream.write(f"{entry}\n")
        self.stream.flush()

    def close(self) -> None:
        self.stream.close()


class ApplicationLogger:
    def __init__(self, sink: LogSink, formatter: LogFormatter, debug_enabled: bool) -> None:
        self.sink = sink
        self.formatter = formatter
        self.debug_enabled = debug_enabled

    def log(self, logger: str, message: str, **context: Any) -> None:
        self._emit("INFO", logger, message, context)

    def debug(self, logger: str, message: str, **context: Any) -> None:
        if self.debug_enabled:
            self._emit("DEBUG", logger, message, context)

    def error(self, logger: str, message: str, **context: Any) -> None:
        self._emit("ERROR", logger, message, context)

    def _emit(
        self,
        level: str,
        logger: str,
        message: str,
        context: dict[str, Any],
    ) -> None:
        event = LogEvent(
            timestamp=datetime.now(timezone.utc),
            level=level,
            logger=logger,
            message=message,
            context=context,
        )
        self.sink.write(self.formatter.format(event))

    def close(self) -> None:
        close = getattr(self.sink, "close", None)
        if close is not None:
            close()


class NamedLogger:
    def __init__(self, name: str) -> None:
        self.name = name

    def log(self, message: str, **context: Any) -> None:
        _application_logger.log(self.name, message, **context)

    def debug(self, message: str, **context: Any) -> None:
        _application_logger.debug(self.name, message, **context)

    def error(self, message: str, **context: Any) -> None:
        _application_logger.error(self.name, message, **context)


_application_logger = ApplicationLogger(
    StdoutLogSink(), TextLogFormatter(), debug_enabled=False
)


def configure_logging(
    *, debug: bool = False, output: str = "stdout", log_format: str = "text"
) -> None:
    """Configure output once the command-line options have been parsed."""
    global _application_logger
    if log_format == "text":
        formatter: LogFormatter = TextLogFormatter()
    elif log_format == "json":
        formatter = JsonLogFormatter()
    else:
        raise ValueError("log_format must be one of: text, json.")

    sink: LogSink
    if output == "stdout":
        sink = StdoutLogSink()
    elif output:
        sink = FileLogSink(Path(output))
    else:
        raise ValueError("log output must be 'stdout' or a file path.")
    _application_logger.close()
    _application_logger = ApplicationLogger(sink, formatter, debug_enabled=debug)


def get_logger(name: str) -> NamedLogger:
    return NamedLogger(name)


def _timestamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _text_value(value: Any) -> str:
    if isinstance(value, str) and value.replace("_", "").replace("-", "").isalnum():
        return value
    return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
