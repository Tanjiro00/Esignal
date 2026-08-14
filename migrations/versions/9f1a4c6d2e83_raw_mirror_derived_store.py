from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9f1a4c6d2e83"
down_revision: str | None = "3e7a1c9d5b42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "raw_api_snapshots",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("video_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("provenance", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["video_id"], ["youtube_videos.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_raw_api_snapshots_video_id", "raw_api_snapshots", ["video_id"], unique=False
    )
    op.create_index(
        "ix_raw_api_snapshots_fetched_at", "raw_api_snapshots", ["fetched_at"], unique=False
    )
    op.create_index(
        "ix_raw_api_snapshots_expires_at", "raw_api_snapshots", ["expires_at"], unique=False
    )

    op.create_table(
        "derived_metric_points",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("subject_type", sa.String(length=16), nullable=False),
        sa.Column("subject_id", sa.String(length=36), nullable=False),
        sa.Column("metric_name", sa.String(length=80), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("window", sa.String(length=24), nullable=False),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scoring_version", sa.String(length=60), nullable=False),
        sa.Column("input_fingerprint", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_derived_metric_points_subject_id",
        "derived_metric_points",
        ["subject_id"],
        unique=False,
    )
    op.create_index(
        "ix_derived_metric_points_computed_at",
        "derived_metric_points",
        ["computed_at"],
        unique=False,
    )
    op.create_index(
        "ix_derived_metric_points_scoring_version",
        "derived_metric_points",
        ["scoring_version"],
        unique=False,
    )
    op.create_index(
        "ix_derived_metric_points_subject",
        "derived_metric_points",
        ["subject_type", "subject_id", "metric_name", "computed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_derived_metric_points_subject", table_name="derived_metric_points")
    op.drop_index(
        "ix_derived_metric_points_scoring_version", table_name="derived_metric_points"
    )
    op.drop_index("ix_derived_metric_points_computed_at", table_name="derived_metric_points")
    op.drop_index("ix_derived_metric_points_subject_id", table_name="derived_metric_points")
    op.drop_table("derived_metric_points")

    op.drop_index("ix_raw_api_snapshots_expires_at", table_name="raw_api_snapshots")
    op.drop_index("ix_raw_api_snapshots_fetched_at", table_name="raw_api_snapshots")
    op.drop_index("ix_raw_api_snapshots_video_id", table_name="raw_api_snapshots")
    op.drop_table("raw_api_snapshots")
