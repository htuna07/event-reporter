from collections.abc import Sequence
from datetime import datetime

from activity_reporter.ports import EventReader
from activity_reporter.logging import get_logger
from activity_reporter.reporters.base import ReportGenerator

logger = get_logger(__name__)


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
        logger.debug(
            "report.query_started",
            actor_count=len(actors),
            start=start.isoformat(),
            end=end.isoformat(),
        )
        events = self.repository.find(actors, start, end)
        logger.log("report.events_loaded", event_count=len(events))
        return self.generator.generate(events, actors, start, end)
