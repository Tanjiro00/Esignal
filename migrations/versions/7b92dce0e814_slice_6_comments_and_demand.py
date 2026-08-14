"""slice 6 comments and demand

Revision ID: 7b92dce0e814
Revises: 4da7912fb2e0
Create Date: 2026-07-27 15:15:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7b92dce0e814"
down_revision: str | None = "4da7912fb2e0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("youtube_comments") as batch_op:
        batch_op.add_column(sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("author_hash", sa.String(length=64), nullable=True))
        batch_op.add_column(
            sa.Column(
                "fetched_order",
                sa.String(length=16),
                nullable=False,
                server_default="relevance",
            )
        )
        batch_op.create_index("ix_youtube_comments_author_hash", ["author_hash"], unique=False)

    with op.batch_alter_table("demand_clusters") as batch_op:
        batch_op.add_column(
            sa.Column(
                "distinct_commenter_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )

    op.create_table(
        "comment_features",
        sa.Column("comment_id", sa.String(length=36), nullable=False),
        sa.Column("taxonomy", sa.String(length=80), nullable=False),
        sa.Column("demand_probability", sa.Float(), nullable=False),
        sa.Column("spam_probability", sa.Float(), nullable=False),
        sa.Column("sentiment", sa.String(length=24), nullable=False),
        sa.Column("embedding_json", sa.JSON(), nullable=False),
        sa.Column("model_version", sa.String(length=40), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["comment_id"], ["youtube_comments.id"]),
        sa.PrimaryKeyConstraint("comment_id"),
    )
    op.create_index(
        "ix_comment_features_taxonomy",
        "comment_features",
        ["taxonomy"],
        unique=False,
    )
    op.create_index(
        "ix_comment_features_model_version",
        "comment_features",
        ["model_version"],
        unique=False,
    )
    op.create_index(
        "ix_comment_features_calculated_at",
        "comment_features",
        ["calculated_at"],
        unique=False,
    )

    op.create_table(
        "comment_fetch_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("video_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("order", sa.String(length=16), nullable=False),
        sa.Column("idempotency_key", sa.String(length=180), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retained_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("comments_disabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("provider_fetch_ids_json", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["video_id"], ["youtube_videos.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(
        "ix_comment_fetch_runs_video_id",
        "comment_fetch_runs",
        ["video_id"],
        unique=False,
    )
    op.create_index(
        "ix_comment_fetch_runs_provider",
        "comment_fetch_runs",
        ["provider"],
        unique=False,
    )
    op.create_index(
        "ix_comment_fetch_runs_status",
        "comment_fetch_runs",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_comment_fetch_runs_idempotency_key",
        "comment_fetch_runs",
        ["idempotency_key"],
        unique=True,
    )

    op.create_table(
        "demand_pipeline_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=180), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("classifier_version", sa.String(length=40), nullable=False),
        sa.Column("clustering_version", sa.String(length=40), nullable=False),
        sa.Column("candidate_video_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fetched_video_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("comment_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("classified_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cluster_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "provider_failure_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column(
            "processing_lag_seconds",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(
        "ix_demand_pipeline_runs_idempotency_key",
        "demand_pipeline_runs",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_demand_pipeline_runs_status",
        "demand_pipeline_runs",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_demand_pipeline_runs_status", table_name="demand_pipeline_runs")
    op.drop_index(
        "ix_demand_pipeline_runs_idempotency_key",
        table_name="demand_pipeline_runs",
    )
    op.drop_table("demand_pipeline_runs")

    op.drop_index("ix_comment_fetch_runs_idempotency_key", table_name="comment_fetch_runs")
    op.drop_index("ix_comment_fetch_runs_status", table_name="comment_fetch_runs")
    op.drop_index("ix_comment_fetch_runs_provider", table_name="comment_fetch_runs")
    op.drop_index("ix_comment_fetch_runs_video_id", table_name="comment_fetch_runs")
    op.drop_table("comment_fetch_runs")

    op.drop_index("ix_comment_features_calculated_at", table_name="comment_features")
    op.drop_index("ix_comment_features_model_version", table_name="comment_features")
    op.drop_index("ix_comment_features_taxonomy", table_name="comment_features")
    op.drop_table("comment_features")

    with op.batch_alter_table("demand_clusters") as batch_op:
        batch_op.drop_column("distinct_commenter_count")

    with op.batch_alter_table("youtube_comments") as batch_op:
        batch_op.drop_index("ix_youtube_comments_author_hash")
        batch_op.drop_column("fetched_order")
        batch_op.drop_column("author_hash")
        batch_op.drop_column("updated_at")
