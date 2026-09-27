from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from activity_reporter.domain import NormalizedEvent, StoredEvent


class EventWriter(Protocol):
    def upsert(self, events: Sequence[NormalizedEvent]) -> int: ...


class EventReader(Protocol):
    def find(
        self,
        actors: Sequence[str],
        start: datetime,
        end: datetime,
    ) -> list[StoredEvent]: ...
