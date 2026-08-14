"""slice 7 transcript intelligence

Revision ID: c2d8f98b7c11
Revises: 7b92dce0e814
Create Date: 2026-07-27 16:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c2d8f98b7c11"
down_revision: str | None = "7b92dce0e814"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("video_transcripts") as batch_op:
        batch_op.add_column(sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("model_name", sa.String(length=80), nullable=True))
        batch_op.add_column(
            sa.Column("summary_json", sa.JSON(), nullable=False, server_default="{}")
        )
        batch_op.add_column(
            sa.Column("entities_json", sa.JSON(), nullable=False, server_default="[]")
        )
        batch_op.add_column(
            sa.Column("key_claims_json", sa.JSON(), nullable=False, server_default="[]")
        )
        batch_op.add_column(
            sa.Column("use_cases_json", sa.JSON(), nullable=False, server_default="[]")
        )
        batch_op.add_column(
            sa.Column("comparisons_json", sa.JSON(), nullable=False, server_default="[]")
        )
        batch_op.add_column(
            sa.Column(
                "unanswered_questions_json",
                sa.JSON(),
                nullable=False,
                server_default="[]",
            )
        )
        batch_op.add_column(
            sa.Column(
                "narrative_angle",
                sa.String(length=80),
                nullable=False,
                server_default="unknown",
            )
        )
        batch_op.add_column(
            sa.Column(
                "content_format",
                sa.String(length=80),
                nullable=False,
                server_default="unknown",
            )
        )
        batch_op.add_column(
            sa.Column(
                "processing_version",
                sa.String(length=40),
                nullable=False,
                server_default="transcript-processing-v2",
            )
        )
    op.execute("UPDATE video_transcripts SET fetched_at = created_at WHERE fetched_at IS NULL")
    with op.batch_alter_table("video_transcripts") as batch_op:
        batch_op.alter_column("fetched_at", nullable=False)

    op.create_table(
        "transcript_segments",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("transcript_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("start_seconds", sa.Float(), nullable=False),
        sa.Column("end_seconds", sa.Float(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding_json", sa.JSON(), nullable=False),
        sa.Column("is_evidence", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("segment_hash", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["transcript_id"], ["video_transcripts.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("transcript_id", "position"),
    )
    op.create_index(
        "ix_transcript_segments_transcript_id",
        "transcript_segments",
        ["transcript_id"],
    )
    op.create_index(
        "ix_transcript_segments_is_evidence",
        "transcript_segments",
        ["is_evidence"],
    )

    op.create_table(
        "transcript_fetch_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("video_id", sa.String(length=36), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("idempotency_key", sa.String(length=180), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("transcript_id", sa.String(length=36), nullable=True),
        sa.Column("provider_fetch_id", sa.String(length=36), nullable=True),
        sa.Column("language_policy", sa.String(length=120), nullable=False),
        sa.Column("allow_generated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["video_id"], ["youtube_videos.id"]),
        sa.ForeignKeyConstraint(["transcript_id"], ["video_transcripts.id"]),
        sa.ForeignKeyConstraint(["provider_fetch_id"], ["provider_fetches.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    for name, columns, unique in (
        ("ix_transcript_fetch_runs_video_id", ["video_id"], False),
        ("ix_transcript_fetch_runs_provider", ["provider"], False),
        ("ix_transcript_fetch_runs_status", ["status"], False),
        ("ix_transcript_fetch_runs_idempotency_key", ["idempotency_key"], True),
    ):
        op.create_index(name, "transcript_fetch_runs", columns, unique=unique)

    op.create_table(
        "transcript_pipeline_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=180), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("processing_version", sa.String(length=40), nullable=False),
        sa.Column("candidate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("fetched_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("unavailable_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("segment_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("processing_lag_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(
        "ix_transcript_pipeline_runs_idempotency_key",
        "transcript_pipeline_runs",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_transcript_pipeline_runs_status",
        "transcript_pipeline_runs",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_transcript_pipeline_runs_status", table_name="transcript_pipeline_runs")
    op.drop_index(
        "ix_transcript_pipeline_runs_idempotency_key",
        table_name="transcript_pipeline_runs",
    )
    op.drop_table("transcript_pipeline_runs")

    for name in (
        "ix_transcript_fetch_runs_idempotency_key",
        "ix_transcript_fetch_runs_status",
        "ix_transcript_fetch_runs_provider",
        "ix_transcript_fetch_runs_video_id",
    ):
        op.drop_index(name, table_name="transcript_fetch_runs")
    op.drop_table("transcript_fetch_runs")

    op.drop_index("ix_transcript_segments_is_evidence", table_name="transcript_segments")
    op.drop_index("ix_transcript_segments_transcript_id", table_name="transcript_segments")
    op.drop_table("transcript_segments")

    with op.batch_alter_table("video_transcripts") as batch_op:
        for column in (
            "processing_version",
            "content_format",
            "narrative_angle",
            "unanswered_questions_json",
            "comparisons_json",
            "use_cases_json",
            "key_claims_json",
            "entities_json",
            "summary_json",
            "model_name",
            "fetched_at",
        ):
            batch_op.drop_column(column)
