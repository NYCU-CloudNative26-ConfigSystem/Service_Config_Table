"""add environment to config_relation

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-26 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add nullable first so existing rows don't violate NOT NULL
    op.add_column("config_relation", sa.Column("environment", sa.String(20), nullable=True))
    op.execute("UPDATE config_relation SET environment = 'production'")
    op.alter_column("config_relation", "environment", nullable=False)
    op.create_index("ix_config_relation_environment", "config_relation", ["environment"])


def downgrade() -> None:
    op.drop_index("ix_config_relation_environment", "config_relation")
    op.drop_column("config_relation", "environment")
