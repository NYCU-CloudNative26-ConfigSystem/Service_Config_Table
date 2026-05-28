"""template version name and apply support

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-28 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("project_template_version", sa.Column("template_name", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("project_template_version", "template_name")
