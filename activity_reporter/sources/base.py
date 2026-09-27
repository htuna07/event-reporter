from abc import ABC, abstractmethod
from collections.abc import Iterable, Mapping
from datetime import datetime
from typing import Any, ClassVar

from activity_reporter.adapters.base import EventAdapter


class EventSource(ABC):
    name: ClassVar[str]
    adapter: EventAdapter

    @classmethod
    @abstractmethod
    def from_environment(cls, environment: Mapping[str, str]) -> "EventSource | None":
        raise NotImplementedError

    @abstractmethod
    def fetch(self, start: datetime, end: datetime) -> Iterable[dict[str, Any]]:
        raise NotImplementedError
