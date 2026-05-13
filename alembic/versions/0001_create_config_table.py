"""create config_table

Revision ID: 0001
Revises:
Create Date: 2026-05-13 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "config_table",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("from_id", sa.String(255), nullable=False),
        sa.Column("to_id", sa.String(255), nullable=False),
        sa.Column("creator", sa.String(255), nullable=False),
        sa.Column("company", sa.String(255), nullable=False),
        sa.Column(
            "create_time",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
    )
    op.create_index("ix_config_table_from_id", "config_table", ["from_id"])
    op.create_index("ix_config_table_to_id", "config_table", ["to_id"])
    op.create_index("ix_config_table_creator", "config_table", ["creator"])
    op.create_index("ix_config_table_company", "config_table", ["company"])


def downgrade() -> None:
    op.drop_index("ix_config_table_company", "config_table")
    op.drop_index("ix_config_table_creator", "config_table")
    op.drop_index("ix_config_table_to_id", "config_table")
    op.drop_index("ix_config_table_from_id", "config_table")
    op.drop_table("config_table")
