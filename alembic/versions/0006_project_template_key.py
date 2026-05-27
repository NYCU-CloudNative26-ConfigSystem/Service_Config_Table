"""project template key

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-25 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_template_key",
        sa.Column("uuid", sa.String(36), primary_key=True),
        sa.Column("proj_id", sa.String(255), sa.ForeignKey("project.proj_id", ondelete="CASCADE"), nullable=False),
        sa.Column("name_node_uuid", sa.String(36), nullable=False),
        sa.Column("alias", sa.String(255), nullable=False),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("date_created", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("proj_id", "name_node_uuid", name="uq_project_template_key"),
    )
    op.create_index("ix_project_template_key_proj_id", "project_template_key", ["proj_id"])


def downgrade() -> None:
    op.drop_index("ix_project_template_key_proj_id", "project_template_key")
    op.drop_table("project_template_key")
