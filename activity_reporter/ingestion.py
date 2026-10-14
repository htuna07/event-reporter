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
        iterator = iter(source.fetch(start, end))

        def write_batch() -> None:
            nonlocal count
            if not batch:
                return
            batch_size = len(batch)
            written = self.repository.upsert(batch)
            count += written
            logger.debug(
                "ingestion.batch_written",
                source=source.name,
                batch_size=batch_size,
                written=written,
                cumulative_count=count,
            )
            batch.clear()

        while True:
            try:
                payload = next(iterator)
            except StopIteration:
                break
            except Exception:
                write_batch()
                raise
            try:
                batch.append(source.adapter.adapt(payload))
            except Exception as error:
                logger.error(
                    "ingestion.event_adaptation_failed",
                    source=source.name,
                    error_type=type(error).__name__,
                )
                write_batch()
                raise
            if len(batch) == self.batch_size:
                write_batch()
        write_batch()
        return count
