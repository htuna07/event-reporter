import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from activity_reporter.domain import StoredEvent
from activity_reporter.logging import get_logger

logger = get_logger(__name__)


REPORT_INSTRUCTIONS = """
You create activity reports from normalized event logs.
Use only the supplied events.
Group related work instead of describing every event separately.
Give priority to write, create, update, and collaboration events;
treat read-only events as operational activities.
Return a title, an Actions bullet list, and a short Summary.
Each bullet in the actions must start past tense.
Each bullet must focus on what was done.
If there are no events, return a title followed only by 'Nothing has been done.'
"""


class ReportGenerator(Protocol):
    def generate(
        self,
        events: Sequence[StoredEvent],
        actors: Sequence[str],
        start: datetime,
        end: datetime,
    ) -> str: ...


@dataclass(frozen=True, slots=True)
class ReportGenerationParameters:
    model: str
    max_events: int
    max_input_characters: int
    max_tokens: int


class BaseReportGenerator:
    def __init__(self, parameters: ReportGenerationParameters) -> None:
        self.parameters = parameters

    def generate(
        self,
        events: Sequence[StoredEvent],
        actors: Sequence[str],
        start: datetime,
        end: datetime,
    ) -> str:
        logger.debug(
            "report.input_validating",
            event_count=len(events),
            max_events=self.parameters.max_events,
        )
        if len(events) > self.parameters.max_events:
            raise ValueError(
                f"Report query returned {len(events)} events, exceeding "
                f"REPORT_MAX_EVENTS={self.parameters.max_events}. Narrow the report range or "
                "increase the configured limit."
            )
        input_data = json.dumps(
            {
                "actors": list(actors),
                "start": start.isoformat(),
                "end": end.isoformat(),
                "events": [
                    event.common_fields()
                    for event in sorted(events, key=_report_order)
                ],
            },
            ensure_ascii=False,
        )
        if len(input_data) > self.parameters.max_input_characters:
            raise ValueError(
                f"Report input contains {len(input_data)} characters, exceeding "
                "REPORT_MAX_INPUT_CHARACTERS="
                f"{self.parameters.max_input_characters}. Narrow the report range or increase "
                "the configured limit."
            )
        logger.debug(
            "report.input_prepared",
            event_count=len(events),
            input_characters=len(input_data),
        )
        return self._generate(input_data)

    def _generate(self, input_data: str) -> str:
        raise NotImplementedError


def _report_order(event: StoredEvent) -> tuple[int, datetime]:
    priority = {
        "failed": 0,
        "delete": 1,
        "write": 1,
        "collaboration": 2,
        "authentication": 3,
        "read": 4,
    }
    category = "failed" if event.outcome == "failed" else event.activity_kind or ""
    return (priority.get(category, 2), event.timestamp)
