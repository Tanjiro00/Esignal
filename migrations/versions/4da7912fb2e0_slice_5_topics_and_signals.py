"""slice 5 topics and signals

Revision ID: 4da7912fb2e0
Revises: b6a4f27dc8e1
Create Date: 2026-07-27 14:45:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4da7912fb2e0"
down_revision: str | None = "b6a4f27dc8e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "topics",
        sa.Column(
            "centroid_embedding",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
    )
    op.add_column(
        "topics",
        sa.Column(
            "embedding_model",
            sa.String(length=80),
            nullable=False,
            server_default="hashing-embedding-v1",
        ),
    )
    op.add_column(
        "topics",
        sa.Column(
            "embedding_version",
            sa.String(length=40),
            nullable=False,
            server_default="topic-embedding-v1",
        ),
    )
    op.add_column(
        "topics",
        sa.Column(
            "source_kind",
            sa.String(length=16),
            nullable=False,
            server_default="demo",
        ),
    )
    op.create_index("ix_topics_source_kind", "topics", ["source_kind"])
    op.add_column(
        "signals",
        sa.Column(
            "source_kind",
            sa.String(length=16),
            nullable=False,
            server_default="demo",
        ),
    )
    op.create_index("ix_signals_source_kind", "signals", ["source_kind"])

    op.create_table(
        "video_embeddings",
        sa.Column("video_id", sa.String(length=36), nullable=False),
        sa.Column("embedding_version", sa.String(length=40), nullable=False),
        sa.Column("model_name", sa.String(length=80), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("vector_json", sa.JSON(), nullable=False),
        sa.Column("entities_json", sa.JSON(), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["video_id"], ["youtube_videos.id"]),
        sa.PrimaryKeyConstraint("video_id", "embedding_version"),
    )
    op.create_index(
        "ix_video_embeddings_calculated_at",
        "video_embeddings",
        ["calculated_at"],
    )

    op.create_table(
        "topic_pipeline_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("clustering_version", sa.String(length=40), nullable=False),
        sa.Column("embedding_version", sa.String(length=40), nullable=False),
        sa.Column("source_video_count", sa.Integer(), nullable=False),
        sa.Column("eligible_video_count", sa.Integer(), nullable=False),
        sa.Column("topic_count", sa.Integer(), nullable=False),
        sa.Column("signal_count", sa.Integer(), nullable=False),
        sa.Column("clustering_lag_seconds", sa.Integer(), nullable=False),
        sa.Column("signal_generation_lag_seconds", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(
        "ix_topic_pipeline_runs_idempotency_key",
        "topic_pipeline_runs",
        ["idempotency_key"],
    )
    op.create_index(
        "ix_topic_pipeline_runs_status",
        "topic_pipeline_runs",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_topic_pipeline_runs_status", table_name="topic_pipeline_runs")
    op.drop_index(
        "ix_topic_pipeline_runs_idempotency_key",
        table_name="topic_pipeline_runs",
    )
    op.drop_table("topic_pipeline_runs")
    op.drop_index(
        "ix_video_embeddings_calculated_at",
        table_name="video_embeddings",
    )
    op.drop_table("video_embeddings")
    op.drop_index("ix_signals_source_kind", table_name="signals")
    op.drop_column("signals", "source_kind")
    op.drop_index("ix_topics_source_kind", table_name="topics")
    op.drop_column("topics", "source_kind")
    op.drop_column("topics", "embedding_version")
    op.drop_column("topics", "embedding_model")
    op.drop_column("topics", "centroid_embedding")
