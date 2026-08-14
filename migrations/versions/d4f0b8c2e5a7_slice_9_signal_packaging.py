"""slice 9 evidence-constrained signal packaging

Revision ID: d4f0b8c2e5a7
Revises: c3e9a7b1d4f6
Create Date: 2026-07-28 22:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4f0b8c2e5a7"
down_revision: str | None = "c3e9a7b1d4f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "signal_packaging",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("signal_id", sa.String(length=36), nullable=False),
        sa.Column("opportunity_id", sa.String(length=36), nullable=False),
        sa.Column("content_brief_id", sa.String(length=36), nullable=False),
        sa.Column("packaging_json", sa.JSON(), nullable=False),
        sa.Column("evidence_ids_json", sa.JSON(), nullable=False),
        sa.Column("regeneration_counts_json", sa.JSON(), nullable=False),
        sa.Column("packaging_version", sa.String(length=48), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["content_brief_id"], ["content_briefs.id"]),
        sa.ForeignKeyConstraint(["signal_id"], ["signals.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("content_brief_id"),
        sa.UniqueConstraint(
            "workspace_id",
            "signal_id",
            "opportunity_id",
            name="uq_signal_packaging_workspace_opportunity",
        ),
    )
    op.create_index(
        "ix_signal_packaging_workspace_id",
        "signal_packaging",
        ["workspace_id"],
    )
    op.create_index(
        "ix_signal_packaging_signal_id",
        "signal_packaging",
        ["signal_id"],
    )
    op.create_index(
        "ix_signal_packaging_opportunity_id",
        "signal_packaging",
        ["opportunity_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_signal_packaging_opportunity_id", table_name="signal_packaging")
    op.drop_index("ix_signal_packaging_signal_id", table_name="signal_packaging")
    op.drop_index("ix_signal_packaging_workspace_id", table_name="signal_packaging")
    op.drop_table("signal_packaging")
