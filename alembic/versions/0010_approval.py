"""add approval workflow to config_relation

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-26 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: Union[str, None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add nullable first (for backfill), then constrain
    op.add_column("config_relation",
        sa.Column("approval_status", sa.String(20), nullable=True))
    op.execute("UPDATE config_relation SET approval_status = 'approved'")
    op.alter_column("config_relation", "approval_status", nullable=False)
    op.create_index(
        "ix_config_relation_approval_status",
        "config_relation", ["approval_status"]
    )

    op.add_column("config_relation",
        sa.Column("approved_by", sa.String(255), nullable=True))
    op.add_column("config_relation",
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("config_relation",
        sa.Column("rejection_reason", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_index("ix_config_relation_approval_status", "config_relation")
    op.drop_column("config_relation", "rejection_reason")
    op.drop_column("config_relation", "approved_at")
    op.drop_column("config_relation", "approved_by")
    op.drop_column("config_relation", "approval_status")
