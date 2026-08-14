"""slice 6 feedback, evaluation labels, and snapshot buckets

Revision ID: a1c7e5f9b2d4
Revises: f0a4c2d7b9e1
Create Date: 2026-07-28 16:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1c7e5f9b2d4"
down_revision: str | None = "f0a4c2d7b9e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("signal_actions", sa.Column("comment", sa.Text(), nullable=True))
    op.add_column(
        "signal_actions",
        sa.Column("opportunity_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "signal_actions",
        sa.Column(
            "feedback_version",
            sa.String(length=48),
            nullable=False,
            server_default="decision-feedback-v1",
        ),
    )
    op.create_index(
        "ix_signal_actions_opportunity_id",
        "signal_actions",
        ["opportunity_id"],
    )

    op.create_table(
        "evaluation_labels",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("topic_id", sa.String(length=36), nullable=False),
        sa.Column("signal_id", sa.String(length=36), nullable=True),
        sa.Column("reviewer_id", sa.String(length=36), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("label", sa.String(length=48), nullable=False),
        sa.Column("additional_labels_json", sa.JSON(), nullable=False),
        sa.Column("evidence_snapshot_json", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("model_versions_json", sa.JSON(), nullable=False),
        sa.Column("label_version", sa.String(length=48), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["signal_id"], ["signals.id"]),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "topic_id",
            "reviewer_id",
            "as_of",
            name="uq_evaluation_label_reviewer_point_in_time",
        ),
    )
    op.create_index(
        "ix_evaluation_labels_workspace_id",
        "evaluation_labels",
        ["workspace_id"],
    )
    op.create_index(
        "ix_evaluation_labels_topic_id",
        "evaluation_labels",
        ["topic_id"],
    )
    op.create_index(
        "ix_evaluation_labels_signal_id",
        "evaluation_labels",
        ["signal_id"],
    )
    op.create_index(
        "ix_evaluation_labels_reviewer_id",
        "evaluation_labels",
        ["reviewer_id"],
    )
    op.create_index(
        "ix_evaluation_labels_as_of",
        "evaluation_labels",
        ["as_of"],
    )
    op.create_index(
        "ix_evaluation_labels_label",
        "evaluation_labels",
        ["label"],
    )
    op.create_index(
        "ix_evaluation_labels_as_of_label",
        "evaluation_labels",
        ["as_of", "label"],
    )

    op.create_table(
        "topic_snapshot_buckets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("topic_id", sa.String(length=36), nullable=False),
        sa.Column("resolution", sa.String(length=12), nullable=False),
        sa.Column("bucket_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bucket_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_json", sa.JSON(), nullable=False),
        sa.Column("last_json", sa.JSON(), nullable=False),
        sa.Column("min_json", sa.JSON(), nullable=False),
        sa.Column("max_json", sa.JSON(), nullable=False),
        sa.Column("avg_json", sa.JSON(), nullable=False),
        sa.Column("video_count", sa.Integer(), nullable=False),
        sa.Column("channel_count", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("momentum", sa.Float(), nullable=False),
        sa.Column("saturation", sa.Float(), nullable=False),
        sa.Column("stage", sa.String(length=32), nullable=False),
        sa.Column("source_measurement_ids_json", sa.JSON(), nullable=False),
        sa.Column("bucket_version", sa.String(length=48), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "topic_id",
            "resolution",
            "bucket_start",
            name="uq_topic_snapshot_bucket",
        ),
    )
    op.create_index(
        "ix_topic_snapshot_buckets_topic_id",
        "topic_snapshot_buckets",
        ["topic_id"],
    )
    op.create_index(
        "ix_topic_snapshot_buckets_bucket_start",
        "topic_snapshot_buckets",
        ["bucket_start"],
    )
    op.create_index(
        "ix_topic_snapshot_buckets_topic_start",
        "topic_snapshot_buckets",
        ["topic_id", "bucket_start"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_topic_snapshot_buckets_topic_start",
        table_name="topic_snapshot_buckets",
    )
    op.drop_index(
        "ix_topic_snapshot_buckets_bucket_start",
        table_name="topic_snapshot_buckets",
    )
    op.drop_index(
        "ix_topic_snapshot_buckets_topic_id",
        table_name="topic_snapshot_buckets",
    )
    op.drop_table("topic_snapshot_buckets")

    op.drop_index("ix_evaluation_labels_as_of_label", table_name="evaluation_labels")
    op.drop_index("ix_evaluation_labels_label", table_name="evaluation_labels")
    op.drop_index("ix_evaluation_labels_as_of", table_name="evaluation_labels")
    op.drop_index("ix_evaluation_labels_reviewer_id", table_name="evaluation_labels")
    op.drop_index("ix_evaluation_labels_signal_id", table_name="evaluation_labels")
    op.drop_index("ix_evaluation_labels_topic_id", table_name="evaluation_labels")
    op.drop_index("ix_evaluation_labels_workspace_id", table_name="evaluation_labels")
    op.drop_table("evaluation_labels")

    op.drop_index("ix_signal_actions_opportunity_id", table_name="signal_actions")
    op.drop_column("signal_actions", "feedback_version")
    op.drop_column("signal_actions", "opportunity_id")
    op.drop_column("signal_actions", "comment")
