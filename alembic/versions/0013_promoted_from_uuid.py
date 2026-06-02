"""add promoted_from_uuid to config_relation

Revision ID: 0013
Revises: 0012
Create Date: 2026-06-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("config_relation", sa.Column("promoted_from_uuid", sa.String(length=36), nullable=True))


def downgrade() -> None:
    op.drop_column("config_relation", "promoted_from_uuid")
