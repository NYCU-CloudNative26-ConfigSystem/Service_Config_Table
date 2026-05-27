"""company schema

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-24 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "company",
        sa.Column("uuid", sa.String(36), primary_key=True),
        sa.Column("cmp_id", sa.String(255), nullable=False, unique=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("date_created", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_company_cmp_id", "company", ["cmp_id"])


def downgrade() -> None:
    op.drop_index("ix_company_cmp_id", "company")
    op.drop_table("company")
