"""slice B blind backtest outcomes and quality reports

Revision ID: d7b4e1c9a203
Revises: c6e91a4f2d73
Create Date: 2026-08-07 12:45:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d7b4e1c9a203"
down_revision: str | None = "c6e91a4f2d73"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "backtest_outcomes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("checkpoint_id", sa.String(length=36), nullable=False),
        sa.Column("candidate_key", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("fired", sa.Boolean(), nullable=False),
        sa.Column("label_method", sa.String(length=64), nullable=False),
        sa.Column("supply_growth_ratio", sa.Float(), nullable=False),
        sa.Column("peak_lift", sa.Float(), nullable=False),
        sa.Column("fired_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("horizon_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evaluation_as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("evidence_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('evaluated', 'insufficient_followup', 'insufficient_evidence')",
            name="ck_backtest_outcomes_status",
        ),
        sa.CheckConstraint(
            "supply_growth_ratio >= 0 AND peak_lift >= 0",
            name="ck_backtest_outcomes_nonnegative_metrics",
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
            name="uq_backtest_outcomes_checkpoint_candidate",
        ),
    )
    op.create_index(
        "ix_backtest_outcomes_checkpoint_id",
        "backtest_outcomes",
        ["checkpoint_id"],
        unique=False,
    )
    op.create_index(
        "ix_backtest_outcomes_status",
        "backtest_outcomes",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_backtest_outcomes_fired",
        "backtest_outcomes",
        ["fired"],
        unique=False,
    )
    op.create_index(
        "ix_backtest_outcomes_fired_at",
        "backtest_outcomes",
        ["fired_at"],
        unique=False,
    )
    op.create_index(
        "ix_backtest_outcomes_evidence_hash",
        "backtest_outcomes",
        ["evidence_hash"],
        unique=False,
    )
    op.create_index(
        "ix_backtest_outcomes_checkpoint_status_fired",
        "backtest_outcomes",
        ["checkpoint_id", "status", "fired"],
        unique=False,
    )

    op.create_table(
        "backtest_reports",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("report_version", sa.String(length=64), nullable=False),
        sa.Column("algorithm_version", sa.String(length=64), nullable=False),
        sa.Column("label_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("checkpoint_ids_json", sa.JSON(), nullable=False),
        sa.Column("metrics_json", sa.JSON(), nullable=False),
        sa.Column("gate_json", sa.JSON(), nullable=False),
        sa.Column("markdown_report", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('success', 'insufficient_data')",
            name="ck_backtest_reports_status",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_backtest_reports_idempotency_key",
        "backtest_reports",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_backtest_reports_content_hash",
        "backtest_reports",
        ["content_hash"],
        unique=False,
    )
    op.create_index(
        "ix_backtest_reports_status",
        "backtest_reports",
        ["status"],
        unique=False,
    )
    op.create_index(
        "ix_backtest_reports_status_created",
        "backtest_reports",
        ["status", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_backtest_reports_status_created", table_name="backtest_reports")
    op.drop_index("ix_backtest_reports_status", table_name="backtest_reports")
    op.drop_index("ix_backtest_reports_content_hash", table_name="backtest_reports")
    op.drop_index("ix_backtest_reports_idempotency_key", table_name="backtest_reports")
    op.drop_table("backtest_reports")

    op.drop_index(
        "ix_backtest_outcomes_checkpoint_status_fired",
        table_name="backtest_outcomes",
    )
    op.drop_index("ix_backtest_outcomes_evidence_hash", table_name="backtest_outcomes")
    op.drop_index("ix_backtest_outcomes_fired_at", table_name="backtest_outcomes")
    op.drop_index("ix_backtest_outcomes_fired", table_name="backtest_outcomes")
    op.drop_index("ix_backtest_outcomes_status", table_name="backtest_outcomes")
    op.drop_index("ix_backtest_outcomes_checkpoint_id", table_name="backtest_outcomes")
    op.drop_table("backtest_outcomes")
