"""template version

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-25 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create version tables first (config_relation FK depends on them)
    op.create_table(
        "project_template_version",
        sa.Column("uuid", sa.String(36), primary_key=True),
        sa.Column("proj_id", sa.String(255), sa.ForeignKey("project.proj_id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer, nullable=False),
        sa.Column("latest", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("date_created", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ptv_proj_id", "project_template_version", ["proj_id"])

    op.create_table(
        "project_template_version_key",
        sa.Column("uuid", sa.String(36), primary_key=True),
        sa.Column("template_version_uuid", sa.String(36), sa.ForeignKey("project_template_version.uuid", ondelete="CASCADE"), nullable=False),
        sa.Column("alias", sa.String(255), nullable=False),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_ptvk_version_uuid", "project_template_version_key", ["template_version_uuid"])

    # 2. Add nullable FK column to config_relation
    op.add_column("config_relation", sa.Column("template_version_uuid", sa.String(36), nullable=True))
    op.create_foreign_key(
        "fk_config_relation_template_version",
        "config_relation", "project_template_version",
        ["template_version_uuid"], ["uuid"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_config_relation_template_version", "config_relation", type_="foreignkey")
    op.drop_column("config_relation", "template_version_uuid")
    op.drop_index("ix_ptvk_version_uuid", "project_template_version_key")
    op.drop_table("project_template_version_key")
    op.drop_index("ix_ptv_proj_id", "project_template_version")
    op.drop_table("project_template_version")
