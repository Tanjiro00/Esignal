"""slice 5 microtopics and content gaps

Revision ID: f0a4c2d7b9e1
Revises: d8e63f90a2b7
Create Date: 2026-07-28 14:15:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f0a4c2d7b9e1"
down_revision: str | None = "d8e63f90a2b7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "topics",
        sa.Column(
            "identity_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.add_column(
        "topics",
        sa.Column(
            "specificity_score",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "topics",
        sa.Column(
            "thesis_support_ratio",
            sa.Float(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "topics",
        sa.Column(
            "visibility_reason_codes_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
    )

    op.create_table(
        "topic_content_patterns",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("topic_id", sa.String(length=36), nullable=False),
        sa.Column("video_id", sa.String(length=36), nullable=False),
        sa.Column("pattern_key", sa.String(length=160), nullable=False),
        sa.Column("pattern_json", sa.JSON(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("model_version", sa.String(length=48), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"]),
        sa.ForeignKeyConstraint(["video_id"], ["youtube_videos.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "topic_id",
            "video_id",
            "model_version",
            name="uq_topic_content_pattern_version",
        ),
    )
    op.create_index(
        "ix_topic_content_patterns_topic_id",
        "topic_content_patterns",
        ["topic_id"],
    )
    op.create_index(
        "ix_topic_content_patterns_video_id",
        "topic_content_patterns",
        ["video_id"],
    )
    op.create_index(
        "ix_topic_content_patterns_pattern_key",
        "topic_content_patterns",
        ["pattern_key"],
    )
    op.create_index(
        "ix_topic_content_patterns_model_version",
        "topic_content_patterns",
        ["model_version"],
    )
    op.create_index(
        "ix_topic_content_patterns_calculated_at",
        "topic_content_patterns",
        ["calculated_at"],
    )

    op.create_table(
        "topic_content_gaps",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("topic_id", sa.String(length=36), nullable=False),
        sa.Column("gap_key", sa.String(length=160), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("occupied_pattern_json", sa.JSON(), nullable=False),
        sa.Column("open_gap_json", sa.JSON(), nullable=False),
        sa.Column("score_components_json", sa.JSON(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("model_version", sa.String(length=48), nullable=False),
        sa.Column("ranking_version", sa.String(length=48), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "topic_id",
            "gap_key",
            "model_version",
            name="uq_topic_content_gap_version",
        ),
    )
    op.create_index(
        "ix_topic_content_gaps_workspace_id",
        "topic_content_gaps",
        ["workspace_id"],
    )
    op.create_index(
        "ix_topic_content_gaps_topic_id",
        "topic_content_gaps",
        ["topic_id"],
    )
    op.create_index(
        "ix_topic_content_gaps_gap_key",
        "topic_content_gaps",
        ["gap_key"],
    )
    op.create_index(
        "ix_topic_content_gaps_status",
        "topic_content_gaps",
        ["status"],
    )
    op.create_index(
        "ix_topic_content_gaps_model_version",
        "topic_content_gaps",
        ["model_version"],
    )
    op.create_index(
        "ix_topic_content_gaps_calculated_at",
        "topic_content_gaps",
        ["calculated_at"],
    )
    op.create_index(
        "ix_topic_content_gaps_workspace_topic_rank",
        "topic_content_gaps",
        ["workspace_id", "topic_id", "rank"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_topic_content_gaps_workspace_topic_rank",
        table_name="topic_content_gaps",
    )
    op.drop_index("ix_topic_content_gaps_calculated_at", table_name="topic_content_gaps")
    op.drop_index("ix_topic_content_gaps_model_version", table_name="topic_content_gaps")
    op.drop_index("ix_topic_content_gaps_status", table_name="topic_content_gaps")
    op.drop_index("ix_topic_content_gaps_gap_key", table_name="topic_content_gaps")
    op.drop_index("ix_topic_content_gaps_topic_id", table_name="topic_content_gaps")
    op.drop_index("ix_topic_content_gaps_workspace_id", table_name="topic_content_gaps")
    op.drop_table("topic_content_gaps")

    op.drop_index(
        "ix_topic_content_patterns_calculated_at",
        table_name="topic_content_patterns",
    )
    op.drop_index(
        "ix_topic_content_patterns_model_version",
        table_name="topic_content_patterns",
    )
    op.drop_index(
        "ix_topic_content_patterns_pattern_key",
        table_name="topic_content_patterns",
    )
    op.drop_index(
        "ix_topic_content_patterns_video_id",
        table_name="topic_content_patterns",
    )
    op.drop_index(
        "ix_topic_content_patterns_topic_id",
        table_name="topic_content_patterns",
    )
    op.drop_table("topic_content_patterns")

    op.drop_column("topics", "visibility_reason_codes_json")
    op.drop_column("topics", "thesis_support_ratio")
    op.drop_column("topics", "specificity_score")
    op.drop_column("topics", "identity_json")
