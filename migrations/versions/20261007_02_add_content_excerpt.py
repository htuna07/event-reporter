"""add safe content excerpt

Revision ID: 20261007_02
Revises: 20261007_01
Create Date: 2026-10-07
"""

from alembic import op
import sqlalchemy as sa

revision = "20261007_02"
down_revision = "20261007_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("events", sa.Column("content_excerpt", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("events", "content_excerpt")
