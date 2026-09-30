import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from activity_reporter.domain import StoredEvent


REPORT_INSTRUCTIONS = (
    "You create concise activity reports from normalized event logs. "
    "Use only the supplied events. Group related work instead of describing "
    "every event separately. Return a title, an Actions bullet list, and a "
    "short Summary. If there are no events, return a title followed only by "
    "Nothing has been done."
)


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
                "events": [event.common_fields() for event in events],
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
        return self._generate(input_data)

    def _generate(self, input_data: str) -> str:
        raise NotImplementedError
