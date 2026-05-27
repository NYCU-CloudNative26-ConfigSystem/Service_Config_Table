"""project company schema

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-24 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project",
        sa.Column("uuid", sa.String(36), primary_key=True),
        sa.Column("proj_id", sa.String(255), nullable=False, unique=True),
        sa.Column("display_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("date_created", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_project_proj_id", "project", ["proj_id"])

    op.create_table(
        "project_company",
        sa.Column("uuid", sa.String(36), primary_key=True),
        sa.Column(
            "proj_id",
            sa.String(255),
            sa.ForeignKey("project.proj_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("cmp_id", sa.String(255), nullable=False),
        sa.Column("date_added", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("proj_id", "cmp_id", name="uq_project_company"),
    )
    op.create_index("ix_project_company_proj_id", "project_company", ["proj_id"])
    op.create_index("ix_project_company_cmp_id", "project_company", ["cmp_id"])


def downgrade() -> None:
    op.drop_index("ix_project_company_cmp_id", "project_company")
    op.drop_index("ix_project_company_proj_id", "project_company")
    op.drop_table("project_company")
    op.drop_index("ix_project_proj_id", "project")
    op.drop_table("project")
