from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True, slots=True)
class NormalizedEvent:
    external_id: str
    source: str
    timestamp: datetime
    actor: str
    action: str
    resource: str
    raw_payload: dict[str, Any]

    def __post_init__(self) -> None:
        if not all(
            (self.external_id, self.source, self.actor, self.action, self.resource)
        ):
            raise ValueError("Common event fields cannot be empty.")
        if self.timestamp.tzinfo is None:
            raise ValueError("Event timestamps must be timezone-aware.")
        object.__setattr__(self, "timestamp", self.timestamp.astimezone(timezone.utc))


@dataclass(frozen=True, slots=True)
class StoredEvent(NormalizedEvent):
    id: int

    def common_fields(self) -> dict[str, str | int]:
        return {
            "id": self.id,
            "external_id": self.external_id,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "actor": self.actor,
            "action": self.action,
            "resource": self.resource,
        }
