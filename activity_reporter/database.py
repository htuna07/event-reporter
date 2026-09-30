from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    DateTime,
    Identity,
    Index,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from activity_reporter.domain import NormalizedEvent, StoredEvent
from activity_reporter.logging import get_logger

logger = get_logger(__name__)


class Base(DeclarativeBase):
    pass


class EventRow(Base):
    __tablename__ = "events"
    __table_args__ = (
        UniqueConstraint(
            "source",
            "external_id",
            name="uq_events_source_external_id",
        ),
        Index("ix_events_actor_timestamp", "actor", "timestamp"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(always=True),
        primary_key=True,
    )
    external_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    actor: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(255), nullable=False)
    resource: Mapped[str] = mapped_column(Text, nullable=False)
    raw_payload: Mapped[dict] = mapped_column(JSONB, nullable=False)


class EventRepository:
    def __init__(self, engine: Engine) -> None:
        if engine.dialect.name != "postgresql":
            raise ValueError("EventRepository requires PostgreSQL.")
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
            }
            for event in unique_events
        ]
        statement = insert(EventRow).values(values)
        statement = statement.on_conflict_do_update(
            constraint="uq_events_source_external_id",
            set_={
                "timestamp": statement.excluded.timestamp,
                "actor": statement.excluded.actor,
                "action": statement.excluded.action,
                "resource": statement.excluded.resource,
                "raw_payload": statement.excluded.raw_payload,
            },
        )
        with Session(self.engine) as session:
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
            )
            for row in rows
        ]


def build_repository(database_url: str) -> EventRepository:
    repository = EventRepository(create_engine(database_url, pool_pre_ping=True))
    logger.debug("database.repository_initialized", dialect=repository.engine.dialect.name)
    return repository
