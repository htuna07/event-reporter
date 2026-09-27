from datetime import datetime

from activity_reporter.domain import NormalizedEvent
from activity_reporter.ports import EventWriter
from activity_reporter.sources.base import EventSource


class IngestionService:
    def __init__(self, repository: EventWriter, batch_size: int = 500) -> None:
        self.repository = repository
        self.batch_size = batch_size

    def ingest(self, source: EventSource, start: datetime, end: datetime) -> int:
        count = 0
        batch: list[NormalizedEvent] = []
        for payload in source.fetch(start, end):
            batch.append(source.adapter.adapt(payload))
            if len(batch) == self.batch_size:
                count += self.repository.upsert(batch)
                batch.clear()
        count += self.repository.upsert(batch)
        return count
