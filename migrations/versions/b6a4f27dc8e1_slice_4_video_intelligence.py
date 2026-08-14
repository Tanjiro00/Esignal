"""slice 4 video intelligence

Revision ID: b6a4f27dc8e1
Revises: 8c9d42a2f1a4
Create Date: 2026-07-27 13:10:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b6a4f27dc8e1"
down_revision: str | None = "8c9d42a2f1a4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "youtube_videos",
        sa.Column(
            "discovery_lag_seconds",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "video_snapshots",
        sa.Column(
            "likes_per_1000_views",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "video_snapshots",
        sa.Column(
            "comments_per_1000_views",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "video_snapshots",
        sa.Column(
            "is_estimated",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    op.create_table(
        "video_snapshot_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("video_id", sa.String(length=36), nullable=False),
        sa.Column("scheduled_age_seconds", sa.Integer(), nullable=False),
        sa.Column("run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("provider_fetch_id", sa.String(length=36), nullable=True),
        sa.Column("skip_reason", sa.String(length=120), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["provider_fetch_id"], ["provider_fetches.id"]),
        sa.ForeignKeyConstraint(["video_id"], ["youtube_videos.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "video_id",
            "scheduled_age_seconds",
            name="uq_video_snapshot_job_age",
        ),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(
        "ix_video_snapshot_jobs_video_id",
        "video_snapshot_jobs",
        ["video_id"],
    )
    op.create_index(
        "ix_video_snapshot_jobs_run_at",
        "video_snapshot_jobs",
        ["run_at"],
    )
    op.create_index(
        "ix_video_snapshot_jobs_status",
        "video_snapshot_jobs",
        ["status"],
    )
    op.create_index(
        "ix_video_snapshot_jobs_idempotency_key",
        "video_snapshot_jobs",
        ["idempotency_key"],
    )

    op.create_table(
        "video_features",
        sa.Column("video_id", sa.String(length=36), nullable=False),
        sa.Column("feature_version", sa.String(length=40), nullable=False),
        sa.Column("language_probability", sa.Float(), nullable=False),
        sa.Column("vertical_relevance", sa.Float(), nullable=False),
        sa.Column("outlier_ratio", sa.Float(), nullable=False),
        sa.Column("view_velocity", sa.Float(), nullable=False),
        sa.Column("velocity_acceleration", sa.Float(), nullable=False),
        sa.Column("engagement_rate", sa.Float(), nullable=False),
        sa.Column("novelty_score", sa.Float(), nullable=False),
        sa.Column("spam_probability", sa.Float(), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["video_id"], ["youtube_videos.id"]),
        sa.PrimaryKeyConstraint("video_id", "feature_version"),
    )
    op.create_index(
        "ix_video_features_calculated_at",
        "video_features",
        ["calculated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_video_features_calculated_at", table_name="video_features")
    op.drop_table("video_features")
    op.drop_index(
        "ix_video_snapshot_jobs_idempotency_key",
        table_name="video_snapshot_jobs",
    )
    op.drop_index("ix_video_snapshot_jobs_status", table_name="video_snapshot_jobs")
    op.drop_index("ix_video_snapshot_jobs_run_at", table_name="video_snapshot_jobs")
    op.drop_index(
        "ix_video_snapshot_jobs_video_id",
        table_name="video_snapshot_jobs",
    )
    op.drop_table("video_snapshot_jobs")
    op.drop_column("video_snapshots", "is_estimated")
    op.drop_column("video_snapshots", "comments_per_1000_views")
    op.drop_column("video_snapshots", "likes_per_1000_views")
    op.drop_column("youtube_videos", "discovery_lag_seconds")
