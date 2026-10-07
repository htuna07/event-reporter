"""expand normalized events

Revision ID: 20261007_01
Revises:
Create Date: 2026-10-07
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20261007_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = (
        sa.Column("event_type", sa.String(length=128), nullable=True),
        sa.Column("event_action", sa.String(length=128), nullable=True),
        sa.Column("activity_kind", sa.String(length=32), nullable=True),
        sa.Column("outcome", sa.String(length=32), nullable=True),
        sa.Column("service", sa.String(length=128), nullable=True),
        sa.Column("region", sa.String(length=64), nullable=True),
        sa.Column("resource_type", sa.String(length=128), nullable=True),
        sa.Column("resource_id", sa.String(length=512), nullable=True),
        sa.Column("resource_name", sa.Text(), nullable=True),
        sa.Column("resource_url", sa.Text(), nullable=True),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column("correlation_id", sa.String(length=512), nullable=True),
        sa.Column("attributes", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    for column in columns:
        op.add_column("events", column)
    op.create_index("ix_events_activity_timestamp", "events", ["activity_kind", "timestamp"])
    op.create_index("ix_events_service_region_timestamp", "events", ["service", "region", "timestamp"])


def downgrade() -> None:
    op.drop_index("ix_events_service_region_timestamp", table_name="events")
    op.drop_index("ix_events_activity_timestamp", table_name="events")
    for name in ("attributes", "correlation_id", "title", "resource_url", "resource_name", "resource_id", "resource_type", "region", "service", "outcome", "activity_kind", "event_action", "event_type"):
        op.drop_column("events", name)
