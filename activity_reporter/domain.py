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
    event_type: str | None = None
    event_action: str | None = None
    activity_kind: str | None = None
    outcome: str | None = None
    service: str | None = None
    region: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    resource_name: str | None = None
    resource_url: str | None = None
    title: str | None = None
    content_excerpt: str | None = None
    correlation_id: str | None = None
    attributes: dict[str, Any] | None = None

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
    id: int = 0

    def common_fields(self) -> dict[str, str | int]:
        fields = {
            "id": self.id,
            "external_id": self.external_id,
            "source": self.source,
            "timestamp": self.timestamp.isoformat(),
            "actor": self.actor,
            "action": self.action,
            "resource": self.resource,
        }
        fields.update(
            {
                key: value
                for key, value in {
                    "event_type": self.event_type,
                    "event_action": self.event_action,
                    "activity_kind": self.activity_kind,
                    "outcome": self.outcome,
                    "service": self.service,
                    "region": self.region,
                    "resource_type": self.resource_type,
                    "resource_id": self.resource_id,
                    "resource_name": self.resource_name,
                    "resource_url": self.resource_url,
                    "title": self.title,
                    "content_excerpt": self.content_excerpt,
                    "correlation_id": self.correlation_id,
                    "attributes": self.attributes,
                }.items()
                if value is not None
            }
        )
        return fields
