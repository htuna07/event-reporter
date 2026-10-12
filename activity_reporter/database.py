from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import (
    BigInteger,
    DateTime,
    Identity,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    select,
)
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine, URL, make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from sqlalchemy.types import TypeDecorator

from activity_reporter.domain import NormalizedEvent, StoredEvent
from activity_reporter.logging import get_logger

logger = get_logger(__name__)


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator[datetime]):
    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect):
        return dialect.type_descriptor(DateTime(timezone=True))

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Event timestamps must be timezone-aware.")
        return value.astimezone(timezone.utc)

    def process_result_value(
        self,
        value: datetime | None,
        dialect,
    ) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


JSON_DOCUMENT = JSON().with_variant(JSONB(), "postgresql")
EVENT_ID = BigInteger().with_variant(Integer(), "sqlite")


class EventRow(Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint(
            "source",
            "external_id",
            name="uq_events_source_external_id",
        ),
        Index("ix_events_actor_timestamp", "actor", "timestamp"),
        Index("ix_events_activity_timestamp", "activity_kind", "timestamp"),
        Index("ix_events_service_region_timestamp", "service", "region", "timestamp"),
    )

    id: Mapped[int] = mapped_column(
        EVENT_ID,
        Identity(always=True),
        primary_key=True,
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    resource: Mapped[str] = mapped_column(Text, nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSON_DOCUMENT, nullable=False)
    event_type: Mapped[str | None] = mapped_column(String(128))
    event_action: Mapped[str | None] = mapped_column(String(128))
    activity_kind: Mapped[str | None] = mapped_column(String(32))
    outcome: Mapped[str | None] = mapped_column(String(32))
    service: Mapped[str | None] = mapped_column(String(128))
    region: Mapped[str | None] = mapped_column(String(64))
    resource_type: Mapped[str | None] = mapped_column(String(128))
    resource_id: Mapped[str | None] = mapped_column(String(512))
    resource_name: Mapped[str | None] = mapped_column(Text)
    resource_url: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    content_excerpt: Mapped[str | None] = mapped_column(Text)
    correlation_id: Mapped[str | None] = mapped_column(String(512))
    attributes: Mapped[dict | None] = mapped_column(JSON_DOCUMENT)


class EventRepository:
    def __init__(self, engine: Engine) -> None:
        if engine.dialect.name not in {"postgresql", "sqlite"}:
            raise ValueError("EventRepository supports PostgreSQL and SQLite.")
        self.engine = engine

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    def upsert(self, events: Sequence[NormalizedEvent]) -> int:
        if not events:
            return 0
        unique_events = {
            (event.source, event.external_id): event for event in events
        }.values()
        values = [
            {
                "source": event.source,
                "external_id": event.external_id,
                "timestamp": event.timestamp,
                "actor": event.actor,
                "action": event.action,
                "resource": event.resource,
                "raw_payload": event.raw_payload,
                "event_type": event.event_type,
                "event_action": event.event_action,
                "activity_kind": event.activity_kind,
                "outcome": event.outcome,
                "service": event.service,
                "region": event.region,
                "resource_type": event.resource_type,
                "resource_id": event.resource_id,
                "resource_name": event.resource_name,
                "resource_url": event.resource_url,
                "title": event.title,
                "content_excerpt": event.content_excerpt,
                "correlation_id": event.correlation_id,
                "attributes": event.attributes,
            }
            for event in unique_events
        ]
        dialect = self.engine.dialect.name
        chunk_size = (
            max(1, 900 // len(values[0]))
            if dialect == "sqlite"
            else len(values)
        )
        value_chunks = (
            values[index : index + chunk_size]
            for index in range(0, len(values), chunk_size)
        )
        with Session(self.engine) as session:
            for value_chunk in value_chunks:
                if dialect == "postgresql":
                    statement = postgresql.insert(EventRow).values(value_chunk)
                else:
                    statement = sqlite.insert(EventRow).values(value_chunk)
                statement = statement.on_conflict_do_update(
                    index_elements=[EventRow.source, EventRow.external_id],
                    set_={
                        "timestamp": statement.excluded.timestamp,
                        "actor": statement.excluded.actor,
                        "action": statement.excluded.action,
                        "resource": statement.excluded.resource,
                        "raw_payload": statement.excluded.raw_payload,
                        "event_type": statement.excluded.event_type,
                        "event_action": statement.excluded.event_action,
                        "activity_kind": statement.excluded.activity_kind,
                        "outcome": statement.excluded.outcome,
                        "service": statement.excluded.service,
                        "region": statement.excluded.region,
                        "resource_type": statement.excluded.resource_type,
                        "resource_id": statement.excluded.resource_id,
                        "resource_name": statement.excluded.resource_name,
                        "resource_url": statement.excluded.resource_url,
                        "title": statement.excluded.title,
                        "content_excerpt": statement.excluded.content_excerpt,
                        "correlation_id": statement.excluded.correlation_id,
                        "attributes": statement.excluded.attributes,
                    },
                )
                session.execute(statement)
            session.commit()
        logger.debug(
            "database.events_upserted",
            received_count=len(events),
            unique_count=len(values),
        )
        return len(values)

    def find(
        self,
        actors: Sequence[str],
        start: datetime,
        end: datetime,
    ) -> list[StoredEvent]:
        statement = (
            select(EventRow)
            .where(
                EventRow.actor.in_(actors),
                EventRow.timestamp >= start,
                EventRow.timestamp < end,
            )
            .order_by(EventRow.timestamp, EventRow.source, EventRow.external_id)
        )
        with Session(self.engine) as session:
            rows = session.scalars(statement).all()
        logger.debug(
            "database.events_found",
            actor_count=len(actors),
            start=start.isoformat(),
            end=end.isoformat(),
            result_count=len(rows),
        )
        return [
            StoredEvent(
                id=row.id,
                external_id=row.external_id,
                source=row.source,
                timestamp=row.timestamp,
                actor=row.actor,
                action=row.action,
                resource=row.resource,
                raw_payload=row.raw_payload,
                event_type=row.event_type,
                event_action=row.event_action,
                activity_kind=row.activity_kind,
                outcome=row.outcome,
                service=row.service,
                region=row.region,
                resource_type=row.resource_type,
                resource_id=row.resource_id,
                resource_name=row.resource_name,
                resource_url=row.resource_url,
                title=row.title,
                content_excerpt=row.content_excerpt,
                correlation_id=row.correlation_id,
                attributes=row.attributes,
            )
            for row in rows
        ]


def build_repository(database_url: str) -> EventRepository:
    url: URL = make_url(database_url)
    if url.get_backend_name() not in {"postgresql", "sqlite"}:
        raise ValueError("DATABASE_URL must select PostgreSQL or SQLite.")
    if (
        url.get_backend_name() == "sqlite"
        and url.database not in (None, "", ":memory:")
    ):
        if not url.database.startswith("file:"):
            Path(url.database).expanduser().resolve().parent.mkdir(
                parents=True,
                exist_ok=True,
            )
    repository = EventRepository(create_engine(url, pool_pre_ping=True))
    logger.debug("database.repository_initialized", dialect=repository.engine.dialect.name)
    return repository
