from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, ClassVar

from activity_reporter.domain import NormalizedEvent


class EventAdapter(ABC):
    source: ClassVar[str]

    @abstractmethod
    def adapt(self, payload: dict[str, Any]) -> NormalizedEvent:
        raise NotImplementedError


def json_safe(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value
