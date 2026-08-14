"""expand signal evidence version

Revision ID: e52c91ab74d0
Revises: d31b7a6c9e42
Create Date: 2026-07-27 19:35:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e52c91ab74d0"
down_revision: str | None = "d31b7a6c9e42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("signals") as batch_op:
        batch_op.alter_column(
            "evidence_version",
            existing_type=sa.String(length=40),
            type_=sa.String(length=120),
            existing_nullable=False,
        )


def downgrade() -> None:
    with op.batch_alter_table("signals") as batch_op:
        batch_op.alter_column(
            "evidence_version",
            existing_type=sa.String(length=120),
            type_=sa.String(length=40),
            existing_nullable=False,
        )
