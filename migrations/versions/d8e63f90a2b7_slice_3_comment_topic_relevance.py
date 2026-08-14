"""slice 3 comment topic relevance

Revision ID: d8e63f90a2b7
Revises: c4a72b8d9e11
Create Date: 2026-07-28 13:20:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d8e63f90a2b7"
down_revision: str | None = "c4a72b8d9e11"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "comment_topic_relevance",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("comment_id", sa.String(length=36), nullable=False),
        sa.Column("topic_id", sa.String(length=36), nullable=False),
        sa.Column("video_id", sa.String(length=36), nullable=False),
        sa.Column("is_relevant", sa.Boolean(), nullable=False),
        sa.Column("relevance_score", sa.Float(), nullable=False),
        sa.Column("comment_topic_semantic_similarity", sa.Float(), nullable=False),
        sa.Column("comment_video_semantic_similarity", sa.Float(), nullable=False),
        sa.Column("entity_overlap_score", sa.Float(), nullable=False),
        sa.Column("claim_support_score", sa.Float(), nullable=False),
        sa.Column("intent_actionability_score", sa.Float(), nullable=False),
        sa.Column("duplicate_or_echo_probability", sa.Float(), nullable=False),
        sa.Column("spam_probability", sa.Float(), nullable=False),
        sa.Column("intent", sa.String(length=80), nullable=False),
        sa.Column("actionability", sa.String(length=16), nullable=False),
        sa.Column("supported_entities_json", sa.JSON(), nullable=False),
        sa.Column("supported_claims_json", sa.JSON(), nullable=False),
        sa.Column("reason_codes_json", sa.JSON(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("model_version", sa.String(length=48), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("override_decision", sa.Boolean(), nullable=True),
        sa.Column("override_reason", sa.String(length=240), nullable=True),
        sa.Column("reviewer_id", sa.String(length=36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["comment_id"], ["youtube_comments.id"]),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"]),
        sa.ForeignKeyConstraint(["video_id"], ["youtube_videos.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "comment_id",
            "topic_id",
            name="uq_comment_topic_relevance_comment_topic",
        ),
    )
    op.create_index(
        "ix_comment_topic_relevance_comment_id",
        "comment_topic_relevance",
        ["comment_id"],
    )
    op.create_index(
        "ix_comment_topic_relevance_input_hash",
        "comment_topic_relevance",
        ["input_hash"],
    )
    op.create_index(
        "ix_comment_topic_relevance_is_relevant",
        "comment_topic_relevance",
        ["is_relevant"],
    )
    op.create_index(
        "ix_comment_topic_relevance_model_version",
        "comment_topic_relevance",
        ["model_version"],
    )
    op.create_index(
        "ix_comment_topic_relevance_topic_effective",
        "comment_topic_relevance",
        ["topic_id", "is_relevant"],
    )
    op.create_index(
        "ix_comment_topic_relevance_topic_id",
        "comment_topic_relevance",
        ["topic_id"],
    )
    op.create_index(
        "ix_comment_topic_relevance_video_id",
        "comment_topic_relevance",
        ["video_id"],
    )

    op.create_table(
        "comment_topic_relevance_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("relevance_id", sa.String(length=36), nullable=False),
        sa.Column("topic_id", sa.String(length=36), nullable=False),
        sa.Column("comment_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("previous_result_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("actor_id", sa.String(length=36), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.String(length=180), nullable=False),
        sa.Column("model_version", sa.String(length=48), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["comment_id"], ["youtube_comments.id"]),
        sa.ForeignKeyConstraint(["relevance_id"], ["comment_topic_relevance.id"]),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_comment_topic_relevance_events_comment_id",
        "comment_topic_relevance_events",
        ["comment_id"],
    )
    op.create_index(
        "ix_comment_topic_relevance_events_event_type",
        "comment_topic_relevance_events",
        ["event_type"],
    )
    op.create_index(
        "ix_comment_topic_relevance_events_idempotency_key",
        "comment_topic_relevance_events",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_comment_topic_relevance_events_relevance_created",
        "comment_topic_relevance_events",
        ["relevance_id", "created_at"],
    )
    op.create_index(
        "ix_comment_topic_relevance_events_relevance_id",
        "comment_topic_relevance_events",
        ["relevance_id"],
    )
    op.create_index(
        "ix_comment_topic_relevance_events_topic_id",
        "comment_topic_relevance_events",
        ["topic_id"],
    )

    op.add_column(
        "demand_pipeline_runs",
        sa.Column(
            "relevance_evaluated_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "demand_pipeline_runs",
        sa.Column(
            "relevance_accepted_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "demand_pipeline_runs",
        sa.Column(
            "relevance_rejected_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "demand_pipeline_runs",
        sa.Column("relevance_model_version", sa.String(length=48), nullable=True),
    )

    op.add_column(
        "demand_clusters",
        sa.Column(
            "visibility_status",
            sa.String(length=24),
            nullable=False,
            server_default="legacy_visible",
        ),
    )
    op.add_column(
        "demand_clusters",
        sa.Column(
            "evidence_strength",
            sa.String(length=16),
            nullable=False,
            server_default="Unverified",
        ),
    )
    op.add_column(
        "demand_clusters",
        sa.Column("median_relevance_score", sa.Float(), nullable=True),
    )
    op.add_column(
        "demand_clusters",
        sa.Column(
            "high_actionability_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "demand_clusters",
        sa.Column("relevance_model_version", sa.String(length=48), nullable=True),
    )
    op.create_index(
        "ix_demand_clusters_visibility_status",
        "demand_clusters",
        ["visibility_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_demand_clusters_visibility_status", table_name="demand_clusters")
    op.drop_column("demand_clusters", "relevance_model_version")
    op.drop_column("demand_clusters", "high_actionability_count")
    op.drop_column("demand_clusters", "median_relevance_score")
    op.drop_column("demand_clusters", "evidence_strength")
    op.drop_column("demand_clusters", "visibility_status")

    op.drop_column("demand_pipeline_runs", "relevance_model_version")
    op.drop_column("demand_pipeline_runs", "relevance_rejected_count")
    op.drop_column("demand_pipeline_runs", "relevance_accepted_count")
    op.drop_column("demand_pipeline_runs", "relevance_evaluated_count")

    op.drop_index(
        "ix_comment_topic_relevance_events_topic_id",
        table_name="comment_topic_relevance_events",
    )
    op.drop_index(
        "ix_comment_topic_relevance_events_relevance_id",
        table_name="comment_topic_relevance_events",
    )
    op.drop_index(
        "ix_comment_topic_relevance_events_relevance_created",
        table_name="comment_topic_relevance_events",
    )
    op.drop_index(
        "ix_comment_topic_relevance_events_idempotency_key",
        table_name="comment_topic_relevance_events",
    )
    op.drop_index(
        "ix_comment_topic_relevance_events_event_type",
        table_name="comment_topic_relevance_events",
    )
    op.drop_index(
        "ix_comment_topic_relevance_events_comment_id",
        table_name="comment_topic_relevance_events",
    )
    op.drop_table("comment_topic_relevance_events")

    op.drop_index(
        "ix_comment_topic_relevance_video_id",
        table_name="comment_topic_relevance",
    )
    op.drop_index(
        "ix_comment_topic_relevance_topic_id",
        table_name="comment_topic_relevance",
    )
    op.drop_index(
        "ix_comment_topic_relevance_topic_effective",
        table_name="comment_topic_relevance",
    )
    op.drop_index(
        "ix_comment_topic_relevance_model_version",
        table_name="comment_topic_relevance",
    )
    op.drop_index(
        "ix_comment_topic_relevance_is_relevant",
        table_name="comment_topic_relevance",
    )
    op.drop_index(
        "ix_comment_topic_relevance_input_hash",
        table_name="comment_topic_relevance",
    )
    op.drop_index(
        "ix_comment_topic_relevance_comment_id",
        table_name="comment_topic_relevance",
    )
    op.drop_table("comment_topic_relevance")
