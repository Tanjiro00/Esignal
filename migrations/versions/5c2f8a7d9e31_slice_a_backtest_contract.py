"""slice A point-in-time backtest contract

Revision ID: 5c2f8a7d9e31
Revises: 3e7a1c9d5b42
Create Date: 2026-08-07 11:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "5c2f8a7d9e31"
down_revision: str | None = "3e7a1c9d5b42"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "backtest_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("source_kind", sa.String(length=16), nullable=False),
        sa.Column("dataset_version", sa.String(length=64), nullable=False),
        sa.Column("code_revision", sa.String(length=80), nullable=False),
        sa.Column("code_dirty", sa.Boolean(), nullable=False),
        sa.Column("migration_revision", sa.String(length=64), nullable=True),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("model_versions_json", sa.JSON(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "source_kind IN ('live', 'demo')",
            name="ck_backtest_runs_source_kind",
        ),
        sa.CheckConstraint(
            "status IN ('running', 'success', 'failed')",
            name="ck_backtest_runs_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_backtest_runs_idempotency_key",
        "backtest_runs",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_backtest_runs_source_kind",
        "backtest_runs",
        ["source_kind"],
        unique=False,
    )
    op.create_index(
        "ix_backtest_runs_status",
        "backtest_runs",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_backtest_runs_started_at",
        "backtest_runs",
        ["started_at"],
        unique=False,
    )
    op.create_index(
        "ix_backtest_runs_status_started",
        "backtest_runs",
        ["status", "started_at"],
        unique=False,
    )

    op.create_table(
        "backtest_checkpoints",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("checkpoint_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("manifest_version", sa.String(length=64), nullable=False),
        sa.Column("manifest_json", sa.JSON(), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("eligible_video_count", sa.Integer(), nullable=False),
        sa.Column("snapshot_count", sa.Integer(), nullable=False),
        sa.Column("prediction_count", sa.Integer(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "eligible_video_count >= 0 AND snapshot_count >= 0 AND prediction_count >= 0",
            name="ck_backtest_checkpoints_nonnegative_counts",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'success', 'failed')",
            name="ck_backtest_checkpoints_status",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["backtest_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "checkpoint_at",
            name="uq_backtest_checkpoints_run_time",
        ),
    )
    op.create_index(
        "ix_backtest_checkpoints_run_id",
        "backtest_checkpoints",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ix_backtest_checkpoints_checkpoint_at",
        "backtest_checkpoints",
        ["checkpoint_at"],
        unique=False,
    )
    op.create_index(
        "ix_backtest_checkpoints_status",
        "backtest_checkpoints",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_backtest_checkpoints_input_hash",
        "backtest_checkpoints",
        ["input_hash"],
        unique=False,
    )
    op.create_index(
        "ix_backtest_checkpoints_run_status_time",
        "backtest_checkpoints",
        ["run_id", "status", "checkpoint_at"],
        unique=False,
    )

    op.create_table(
        "backtest_predictions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("checkpoint_id", sa.String(length=36), nullable=False),
        sa.Column("candidate_key", sa.String(length=160), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("lifecycle_stage", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.String(length=24), nullable=False),
        sa.Column("algorithm_version", sa.String(length=64), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("evidence_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "rank > 0",
            name="ck_backtest_predictions_positive_rank",
        ),
        sa.CheckConstraint(
            "score >= 0 AND score <= 100",
            name="ck_backtest_predictions_score_range",
        ),
        sa.ForeignKeyConstraint(
            ["checkpoint_id"],
            ["backtest_checkpoints.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "checkpoint_id",
            "candidate_key",
            name="uq_backtest_predictions_checkpoint_candidate",
        ),
        sa.UniqueConstraint(
            "checkpoint_id",
            "rank",
            name="uq_backtest_predictions_checkpoint_rank",
        ),
    )
    op.create_index(
        "ix_backtest_predictions_checkpoint_id",
        "backtest_predictions",
        ["checkpoint_id"],
        unique=False,
    )
    op.create_index(
        "ix_backtest_predictions_evidence_hash",
        "backtest_predictions",
        ["evidence_hash"],
        unique=False,
    )
    op.create_index(
        "ix_backtest_predictions_checkpoint_score",
        "backtest_predictions",
        ["checkpoint_id", "score"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_backtest_predictions_checkpoint_score",
        table_name="backtest_predictions",
    )
    op.drop_index(
        "ix_backtest_predictions_evidence_hash",
        table_name="backtest_predictions",
    )
    op.drop_index(
        "ix_backtest_predictions_checkpoint_id",
        table_name="backtest_predictions",
    )
    op.drop_table("backtest_predictions")

    op.drop_index(
        "ix_backtest_checkpoints_run_status_time",
        table_name="backtest_checkpoints",
    )
    op.drop_index(
        "ix_backtest_checkpoints_input_hash",
        table_name="backtest_checkpoints",
    )
    op.drop_index(
        "ix_backtest_checkpoints_status",
        table_name="backtest_checkpoints",
    )
    op.drop_index(
        "ix_backtest_checkpoints_checkpoint_at",
        table_name="backtest_checkpoints",
    )
    op.drop_index(
        "ix_backtest_checkpoints_run_id",
        table_name="backtest_checkpoints",
    )
    op.drop_table("backtest_checkpoints")

    op.drop_index(
        "ix_backtest_runs_status_started",
        table_name="backtest_runs",
    )
    op.drop_index("ix_backtest_runs_started_at", table_name="backtest_runs")
    op.drop_index("ix_backtest_runs_status", table_name="backtest_runs")
    op.drop_index("ix_backtest_runs_source_kind", table_name="backtest_runs")
    op.drop_index(
        "ix_backtest_runs_idempotency_key",
        table_name="backtest_runs",
    )
    op.drop_table("backtest_runs")
