"""backtest cohorts with frozen train and holdout checkpoints

Revision ID: e3a6c8f1b927
Revises: d7b4e1c9a203
Create Date: 2026-08-07 13:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e3a6c8f1b927"
down_revision: str | None = "d7b4e1c9a203"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_topic_snapshots_observed_topic",
        "topic_snapshots",
        ["observed_at", "topic_id"],
        unique=False,
    )
    op.create_table(
        "backtest_cohorts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("source_kind", sa.String(length=16), nullable=False),
        sa.Column("policy_version", sa.String(length=64), nullable=False),
        sa.Column("split_policy_version", sa.String(length=64), nullable=False),
        sa.Column("horizon_days", sa.Integer(), nullable=False),
        sa.Column("checkpoint_count", sa.Integer(), nullable=False),
        sa.Column("train_checkpoint_count", sa.Integer(), nullable=False),
        sa.Column("holdout_checkpoint_count", sa.Integer(), nullable=False),
        sa.Column("dataset_hash", sa.String(length=64), nullable=False),
        sa.Column("coverage_json", sa.JSON(), nullable=False),
        sa.Column("repository_json", sa.JSON(), nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "checkpoint_count >= 0 AND train_checkpoint_count >= 0 "
            "AND holdout_checkpoint_count >= 0 "
            "AND checkpoint_count = train_checkpoint_count + holdout_checkpoint_count",
            name="ck_backtest_cohorts_checkpoint_counts",
        ),
        sa.CheckConstraint(
            "source_kind IN ('live', 'demo')",
            name="ck_backtest_cohorts_source_kind",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'frozen')",
            name="ck_backtest_cohorts_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_backtest_cohorts_idempotency_key",
        "backtest_cohorts",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_backtest_cohorts_status",
        "backtest_cohorts",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_backtest_cohorts_source_kind",
        "backtest_cohorts",
        ["source_kind"],
        unique=False,
    )
    op.create_index(
        "ix_backtest_cohorts_dataset_hash",
        "backtest_cohorts",
        ["dataset_hash"],
        unique=False,
    )
    op.create_index(
        "ix_backtest_cohorts_frozen_at",
        "backtest_cohorts",
        ["frozen_at"],
        unique=False,
    )
    op.create_index(
        "ix_backtest_cohorts_status_created",
        "backtest_cohorts",
        ["status", "created_at"],
        unique=False,
    )

    op.create_table(
        "backtest_cohort_checkpoints",
        sa.Column("cohort_id", sa.String(length=36), nullable=False),
        sa.Column("checkpoint_id", sa.String(length=36), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("split", sa.String(length=16), nullable=False),
        sa.Column("checkpoint_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("horizon_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("outcome_ready_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("coverage_json", sa.JSON(), nullable=False),
        sa.Column("frozen_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "ordinal > 0",
            name="ck_backtest_cohort_checkpoints_ordinal",
        ),
        sa.CheckConstraint(
            "split IN ('train', 'holdout')",
            name="ck_backtest_cohort_checkpoints_split",
        ),
        sa.ForeignKeyConstraint(
            ["checkpoint_id"],
            ["backtest_checkpoints.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["cohort_id"],
            ["backtest_cohorts.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("cohort_id", "checkpoint_id"),
        sa.UniqueConstraint(
            "cohort_id",
            "ordinal",
            name="uq_backtest_cohort_checkpoints_ordinal",
        ),
    )
    op.create_index(
        "ix_backtest_cohort_checkpoints_checkpoint_id",
        "backtest_cohort_checkpoints",
        ["checkpoint_id"],
        unique=False,
    )
    op.create_index(
        "ix_backtest_cohort_checkpoints_split",
        "backtest_cohort_checkpoints",
        ["split"],
        unique=False,
    )
    op.create_index(
        "ix_backtest_cohort_checkpoints_checkpoint_at",
        "backtest_cohort_checkpoints",
        ["checkpoint_at"],
        unique=False,
    )
    op.create_index(
        "ix_backtest_cohort_checkpoints_horizon_end",
        "backtest_cohort_checkpoints",
        ["horizon_end"],
        unique=False,
    )
    op.create_index(
        "ix_backtest_cohort_checkpoints_outcome_ready_at",
        "backtest_cohort_checkpoints",
        ["outcome_ready_at"],
        unique=False,
    )
    op.create_index(
        "ix_backtest_cohort_checkpoints_cohort_split_time",
        "backtest_cohort_checkpoints",
        ["cohort_id", "split", "checkpoint_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_backtest_cohort_checkpoints_cohort_split_time",
        table_name="backtest_cohort_checkpoints",
    )
    op.drop_index(
        "ix_backtest_cohort_checkpoints_outcome_ready_at",
        table_name="backtest_cohort_checkpoints",
    )
    op.drop_index(
        "ix_backtest_cohort_checkpoints_horizon_end",
        table_name="backtest_cohort_checkpoints",
    )
    op.drop_index(
        "ix_backtest_cohort_checkpoints_checkpoint_at",
        table_name="backtest_cohort_checkpoints",
    )
    op.drop_index(
        "ix_backtest_cohort_checkpoints_split",
        table_name="backtest_cohort_checkpoints",
    )
    op.drop_index(
        "ix_backtest_cohort_checkpoints_checkpoint_id",
        table_name="backtest_cohort_checkpoints",
    )
    op.drop_table("backtest_cohort_checkpoints")

    op.drop_index("ix_backtest_cohorts_status_created", table_name="backtest_cohorts")
    op.drop_index("ix_backtest_cohorts_frozen_at", table_name="backtest_cohorts")
    op.drop_index("ix_backtest_cohorts_dataset_hash", table_name="backtest_cohorts")
    op.drop_index("ix_backtest_cohorts_source_kind", table_name="backtest_cohorts")
    op.drop_index("ix_backtest_cohorts_status", table_name="backtest_cohorts")
    op.drop_index("ix_backtest_cohorts_idempotency_key", table_name="backtest_cohorts")
    op.drop_table("backtest_cohorts")
    op.drop_index("ix_topic_snapshots_observed_topic", table_name="topic_snapshots")
