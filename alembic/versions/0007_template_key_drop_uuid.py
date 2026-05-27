"""template key drop uuid

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-25 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("uq_project_template_key", "project_template_key", type_="unique")
    op.drop_column("project_template_key", "name_node_uuid")
    op.create_unique_constraint(
        "uq_project_template_key_alias", "project_template_key", ["proj_id", "alias"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_project_template_key_alias", "project_template_key", type_="unique")
    op.add_column(
        "project_template_key",
        sa.Column("name_node_uuid", sa.String(36), nullable=True),
    )
    op.create_unique_constraint(
        "uq_project_template_key", "project_template_key", ["proj_id", "name_node_uuid"]
    )
