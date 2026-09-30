from datetime import datetime

from activity_reporter.domain import NormalizedEvent
from activity_reporter.logging import get_logger
from activity_reporter.ports import EventWriter
from activity_reporter.sources.base import EventSource

logger = get_logger(__name__)


class IngestionService:
    def __init__(self, repository: EventWriter, batch_size: int = 500) -> None:
        self.repository = repository
        self.batch_size = batch_size

    def ingest(self, source: EventSource, start: datetime, end: datetime) -> int:
        count = 0
        batch: list[NormalizedEvent] = []
        for payload in source.fetch(start, end):
            try:
                batch.append(source.adapter.adapt(payload))
            except Exception as error:
                logger.error(
                    "ingestion.event_adaptation_failed",
                    source=source.name,
                    error_type=type(error).__name__,
                )
                raise
            if len(batch) == self.batch_size:
                written = self.repository.upsert(batch)
                count += written
                logger.debug(
                    "ingestion.batch_written",
                    source=source.name,
                    batch_size=len(batch),
                    written=written,
                    cumulative_count=count,
                )
                batch.clear()
        written = self.repository.upsert(batch)
        count += written
        if batch:
            logger.debug(
                "ingestion.batch_written",
                source=source.name,
                batch_size=len(batch),
                written=written,
                cumulative_count=count,
            )
        return count
