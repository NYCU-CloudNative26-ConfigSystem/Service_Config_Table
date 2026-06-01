"""add name to config_relation

Revision ID: 0014
Revises: 0013
Create Date: 2026-06-02 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("config_relation", sa.Column("name", sa.String(length=255), nullable=True))
    op.create_index("ix_config_relations_name", "config_relation", ["name"])


def downgrade() -> None:
    op.drop_index("ix_config_relations_name", table_name="config_relation")
    op.drop_column("config_relation", "name")
