"""slice 8 automatic outcome detection and updates

Revision ID: c3e9a7b1d4f6
Revises: b2d8f6a0c3e5
Create Date: 2026-07-28 20:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3e9a7b1d4f6"
down_revision: str | None = "b2d8f6a0c3e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "published_outcomes",
        sa.Column("link_status", sa.String(length=24), nullable=False, server_default="active"),
    )
    op.add_column(
        "published_outcomes",
        sa.Column(
            "association_version",
            sa.String(length=48),
            nullable=False,
            server_default="outcome-association-v1",
        ),
    )
    op.add_column(
        "published_outcomes",
        sa.Column(
            "metrics_version",
            sa.String(length=48),
            nullable=False,
            server_default="outcome-metrics-v1",
        ),
    )
    op.add_column(
        "published_outcomes",
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute("UPDATE published_outcomes SET updated_at = created_at WHERE updated_at IS NULL")
    with op.batch_alter_table("published_outcomes") as batch:
        batch.alter_column("updated_at", nullable=False)
        batch.create_index("ix_published_outcomes_link_status", ["link_status"])

    op.create_table(
        "outcome_suggestions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("video_id", sa.String(length=36), nullable=False),
        sa.Column("signal_id", sa.String(length=36), nullable=False),
        sa.Column("suggested_brief_id", sa.String(length=36), nullable=False),
        sa.Column("selected_brief_id", sa.String(length=36), nullable=True),
        sa.Column("outcome_id", sa.String(length=36), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("match_confidence", sa.Float(), nullable=False),
        sa.Column("reason_codes_json", sa.JSON(), nullable=False),
        sa.Column("match_features_json", sa.JSON(), nullable=False),
        sa.Column("baseline_json", sa.JSON(), nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.Column("model_version", sa.String(length=48), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["outcome_id"], ["published_outcomes.id"]),
        sa.ForeignKeyConstraint(["selected_brief_id"], ["content_briefs.id"]),
        sa.ForeignKeyConstraint(["signal_id"], ["signals.id"]),
        sa.ForeignKeyConstraint(["suggested_brief_id"], ["content_briefs.id"]),
        sa.ForeignKeyConstraint(["video_id"], ["youtube_videos.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "video_id",
            name="uq_outcome_suggestion_workspace_video",
        ),
    )
    op.create_index(
        "ix_outcome_suggestions_workspace_id",
        "outcome_suggestions",
        ["workspace_id"],
    )
    op.create_index(
        "ix_outcome_suggestions_video_id",
        "outcome_suggestions",
        ["video_id"],
    )
    op.create_index(
        "ix_outcome_suggestions_status",
        "outcome_suggestions",
        ["status"],
    )
    op.create_index(
        "ix_outcome_suggestions_detected_at",
        "outcome_suggestions",
        ["detected_at"],
    )
    op.create_index(
        "ix_outcome_suggestions_workspace_status",
        "outcome_suggestions",
        ["workspace_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_outcome_suggestions_workspace_status",
        table_name="outcome_suggestions",
    )
    op.drop_index("ix_outcome_suggestions_detected_at", table_name="outcome_suggestions")
    op.drop_index("ix_outcome_suggestions_status", table_name="outcome_suggestions")
    op.drop_index("ix_outcome_suggestions_video_id", table_name="outcome_suggestions")
    op.drop_index("ix_outcome_suggestions_workspace_id", table_name="outcome_suggestions")
    op.drop_table("outcome_suggestions")
    with op.batch_alter_table("published_outcomes") as batch:
        batch.drop_index("ix_published_outcomes_link_status")
    op.drop_column("published_outcomes", "updated_at")
    op.drop_column("published_outcomes", "metrics_version")
    op.drop_column("published_outcomes", "association_version")
    op.drop_column("published_outcomes", "link_status")
