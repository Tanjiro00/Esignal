"""versioned panel membership

Records the observed population as dated facts so the panel can be
reconstructed exactly as it stood on any past date. Rows are never mutated in
place: a departure sets ``left_at`` and keeps the original join.

Revision ID: c3a5b7e1d942
Revises: a7d9e2f4b6c8
Create Date: 2026-08-14 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3a5b7e1d942"
down_revision: str | None = "a7d9e2f4b6c8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "panel_membership",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("channel_id", sa.String(length=36), nullable=False),
        sa.Column("joined_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(length=40), nullable=False),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("left_reason", sa.String(length=40), nullable=True),
        # Whose neighbourhood brought this channel in; null for the niche core.
        sa.Column("owner_workspace_id", sa.String(length=36), nullable=True),
        sa.Column("niche_share", sa.Float(), nullable=True),
        sa.Column("last_polled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["channel_id"], ["youtube_channels.id"]),
        sa.ForeignKeyConstraint(["owner_workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    # Reconstructing the panel on a past date is a range scan over these two.
    op.create_index(
        "ix_panel_membership_window",
        "panel_membership",
        ["joined_at", "left_at"],
        unique=False,
    )
    # The crawler asks "who is due?" on every run.
    op.create_index(
        "ix_panel_membership_polling",
        "panel_membership",
        ["left_at", "last_polled_at"],
        unique=False,
    )
    # A channel may rejoin later, so uniqueness is per open membership only.
    op.create_index(
        "ux_panel_membership_open",
        "panel_membership",
        ["channel_id"],
        unique=True,
        postgresql_where=sa.text("left_at IS NULL"),
        sqlite_where=sa.text("left_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ux_panel_membership_open", table_name="panel_membership")
    op.drop_index("ix_panel_membership_polling", table_name="panel_membership")
    op.drop_index("ix_panel_membership_window", table_name="panel_membership")
    op.drop_table("panel_membership")
