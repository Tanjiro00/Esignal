"""slice 9 channel fit and action loop

Revision ID: f719ef52a8b3
Revises: e84ad09c6721
Create Date: 2026-07-27 17:35:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f719ef52a8b3"
down_revision: str | None = "e84ad09c6721"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "channel_profiles",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("channel_id", sa.String(length=36), nullable=False),
        sa.Column(
            "profile_source",
            sa.String(length=24),
            nullable=False,
            server_default="inferred",
        ),
        sa.Column("audience_description", sa.Text(), nullable=False, server_default=""),
        sa.Column("geography", sa.String(length=16), nullable=False, server_default="US"),
        sa.Column("language", sa.String(length=16), nullable=False, server_default="en"),
        sa.Column("topic_keywords_json", sa.JSON(), nullable=False),
        sa.Column("preferred_formats_json", sa.JSON(), nullable=False),
        sa.Column("creator_expertise_json", sa.JSON(), nullable=False),
        sa.Column("production_capabilities_json", sa.JSON(), nullable=False),
        sa.Column("exclusions_json", sa.JSON(), nullable=False),
        sa.Column("strategic_goals_json", sa.JSON(), nullable=False),
        sa.Column("title_style_json", sa.JSON(), nullable=False),
        sa.Column(
            "normal_duration_min_seconds",
            sa.Integer(),
            nullable=False,
            server_default="480",
        ),
        sa.Column(
            "normal_duration_max_seconds",
            sa.Integer(),
            nullable=False,
            server_default="1800",
        ),
        sa.Column("production_days_min", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("production_days_max", sa.Integer(), nullable=False, server_default="7"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["youtube_channels.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("workspace_id", "channel_id"),
    )
    with op.batch_alter_table("workspace_signal_scores") as batch_op:
        batch_op.add_column(
            sa.Column(
                "fit_version",
                sa.String(length=40),
                nullable=False,
                server_default="channel-fit-v1",
            )
        )
    with op.batch_alter_table("content_briefs") as batch_op:
        batch_op.add_column(sa.Column("opportunity_id", sa.String(length=36), nullable=True))
        batch_op.add_column(
            sa.Column(
                "evidence_version",
                sa.String(length=80),
                nullable=False,
                server_default="unknown",
            )
        )
        batch_op.create_index("ix_content_briefs_opportunity_id", ["opportunity_id"])


def downgrade() -> None:
    with op.batch_alter_table("content_briefs") as batch_op:
        batch_op.drop_index("ix_content_briefs_opportunity_id")
        batch_op.drop_column("evidence_version")
        batch_op.drop_column("opportunity_id")
    with op.batch_alter_table("workspace_signal_scores") as batch_op:
        batch_op.drop_column("fit_version")
    op.drop_table("channel_profiles")
