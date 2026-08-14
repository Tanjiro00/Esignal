"""preserve topic video first and last observation history

Revision ID: a7d9e2f4b6c8
Revises: f4c8a2d6e913
Create Date: 2026-08-10 04:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a7d9e2f4b6c8"
down_revision: str | None = "f4c8a2d6e913"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "topic_video_observations",
        sa.Column("topic_id", sa.String(length=36), nullable=False),
        sa.Column("video_id", sa.String(length=36), nullable=False),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observation_count", sa.Integer(), nullable=False),
        sa.Column("first_observation_quality", sa.String(length=32), nullable=False),
        sa.Column("membership_score", sa.Float(), nullable=False),
        sa.Column("assignment_method", sa.String(length=40), nullable=False),
        sa.Column("evidence_role", sa.String(length=40), nullable=False),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"]),
        sa.ForeignKeyConstraint(["video_id"], ["youtube_videos.id"]),
        sa.PrimaryKeyConstraint("topic_id", "video_id"),
    )
    op.create_index(
        "ix_topic_video_observations_topic_first",
        "topic_video_observations",
        ["topic_id", "first_observed_at"],
        unique=False,
    )
    op.create_index(
        "ix_topic_video_observations_topic_last",
        "topic_video_observations",
        ["topic_id", "last_observed_at"],
        unique=False,
    )
    op.execute(
        sa.text(
            """
            INSERT INTO topic_video_observations (
                topic_id,
                video_id,
                first_observed_at,
                last_observed_at,
                observation_count,
                first_observation_quality,
                membership_score,
                assignment_method,
                evidence_role
            )
            SELECT
                topic_id,
                video_id,
                assigned_at,
                assigned_at,
                1,
                'migration_backfill',
                membership_score,
                assignment_method,
                evidence_role
            FROM topic_video_memberships
            """
        )
    )


def downgrade() -> None:
    op.drop_index(
        "ix_topic_video_observations_topic_last",
        table_name="topic_video_observations",
    )
    op.drop_index(
        "ix_topic_video_observations_topic_first",
        table_name="topic_video_observations",
    )
    op.drop_table("topic_video_observations")
