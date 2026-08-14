"""use bigint for channel views

Revision ID: d31b7a6c9e42
Revises: a8d4c1e29f60
Create Date: 2026-07-27 19:25:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d31b7a6c9e42"
down_revision: str | None = "a8d4c1e29f60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("youtube_channels") as batch_op:
        batch_op.alter_column(
            "view_count",
            existing_type=sa.Integer(),
            type_=sa.BigInteger(),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("youtube_channels") as batch_op:
        batch_op.alter_column(
            "view_count",
            existing_type=sa.BigInteger(),
            type_=sa.Integer(),
            existing_nullable=False,
        )
