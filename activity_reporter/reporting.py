from collections.abc import Sequence
from datetime import datetime

from activity_reporter.ports import EventReader
from activity_reporter.reporters.base import ReportGenerator


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
