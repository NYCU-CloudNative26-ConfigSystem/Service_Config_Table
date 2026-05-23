"""ssot config schema

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-23 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "config_relation",
        sa.Column("uuid", sa.String(36), primary_key=True),
        sa.Column("latest", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("date_created", sa.DateTime(timezone=True), nullable=False),
        sa.Column("date_deleted", sa.DateTime(timezone=True), nullable=True),
        sa.Column("proj_id", sa.String(255), nullable=False),
        sa.Column("cmp_id", sa.String(255), nullable=False),
    )
    op.create_index("ix_config_relation_proj_cmp", "config_relation", ["proj_id", "cmp_id"])
    op.create_index("ix_config_relation_latest", "config_relation", ["latest"])

    op.create_table(
        "config_relation_users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "config_relation_uuid",
            sa.String(36),
            sa.ForeignKey("config_relation.uuid", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(255), nullable=False),
    )
    op.create_index("ix_config_relation_users_cr", "config_relation_users", ["config_relation_uuid"])

    op.create_table(
        "ct",
        sa.Column("uuid", sa.String(36), primary_key=True),
        sa.Column(
            "config_relation_uuid",
            sa.String(36),
            sa.ForeignKey("config_relation.uuid", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("val", sa.String(512), nullable=False),
    )
    op.create_index("ix_ct_config_relation_uuid", "ct", ["config_relation_uuid"])

    op.create_table(
        "gt",
        sa.Column("uuid", sa.String(36), primary_key=True),
        sa.Column("gid", sa.String(255), nullable=False),
        sa.Column("key", sa.String(255), nullable=False),
        sa.Column("val", sa.String(512), nullable=False),
    )
    op.create_index("ix_gt_gid", "gt", ["gid"])


def downgrade() -> None:
    op.drop_index("ix_gt_gid", "gt")
    op.drop_table("gt")
    op.drop_index("ix_ct_config_relation_uuid", "ct")
    op.drop_table("ct")
    op.drop_index("ix_config_relation_users_cr", "config_relation_users")
    op.drop_table("config_relation_users")
    op.drop_index("ix_config_relation_latest", "config_relation")
    op.drop_index("ix_config_relation_proj_cmp", "config_relation")
    op.drop_table("config_relation")
