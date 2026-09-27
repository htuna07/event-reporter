import json
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from anthropic import Anthropic

from activity_reporter.domain import StoredEvent
from activity_reporter.ports import EventReader


class ReportGenerator(Protocol):
    def generate(
        self,
        events: Sequence[StoredEvent],
        actors: Sequence[str],
        start: datetime,
        end: datetime,
    ) -> str: ...


class AnthropicReportGenerator:
    def __init__(
        self,
        api_key: str,
        model: str,
        max_events: int,
        max_input_characters: int,
    ) -> None:
        self.client = Anthropic(api_key=api_key)
        self.model = model
        self.max_events = max_events
        self.max_input_characters = max_input_characters

    def generate(
        self,
        events: Sequence[StoredEvent],
        actors: Sequence[str],
        start: datetime,
        end: datetime,
    ) -> str:
        if len(events) > self.max_events:
            raise ValueError(
                f"Report query returned {len(events)} events, exceeding "
                f"REPORT_MAX_EVENTS={self.max_events}. Narrow the report range or "
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
        if len(input_data) > self.max_input_characters:
            raise ValueError(
                f"Report input contains {len(input_data)} characters, exceeding "
                "REPORT_MAX_INPUT_CHARACTERS="
                f"{self.max_input_characters}. Narrow the report range or increase "
                "the configured limit."
            )
        response = self.client.messages.create(
            model=self.model,
            max_tokens=1500,
            system=(
                "You create concise activity reports from normalized event logs. "
                "Use only the supplied events. Group related work instead of describing "
                "every event separately. Return a title, an Actions bullet list, and a "
                "short Summary. If there are no events, return a title followed only by "
                "Nothing has been done."
            ),
            messages=[
                {
                    "role": "user",
                    "content": input_data,
                }
            ],
        )
        return "".join(block.text for block in response.content if block.type == "text")


class ReportService:
    def __init__(self, repository: EventReader, generator: ReportGenerator) -> None:
        self.repository = repository
        self.generator = generator

    def create(
        self,
        actors: Sequence[str],
        start: datetime,
        end: datetime,
    ) -> str:
        events = self.repository.find(actors, start, end)
        return self.generator.generate(events, actors, start, end)
