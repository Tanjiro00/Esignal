"""slice 12 evidence-grounded LLM intelligence

Revision ID: 6a9d1c4e8b27
Revises: f6b2d0e4a7c9
Create Date: 2026-07-28 17:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6a9d1c4e8b27"
down_revision: str | None = "f6b2d0e4a7c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "llm_intelligence_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task", sa.String(length=48), nullable=False),
        sa.Column("scope_kind", sa.String(length=32), nullable=False),
        sa.Column("scope_id", sa.String(length=160), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=48), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("prompt_version", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("evidence_refs_json", sa.JSON(), nullable=False),
        sa.Column("output_json", sa.JSON(), nullable=False),
        sa.Column("validation_json", sa.JSON(), nullable=False),
        sa.Column("usage_json", sa.JSON(), nullable=False),
        sa.Column("provider_response_id", sa.String(length=160), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "task",
            "scope_kind",
            "scope_id",
            "input_hash",
            "prompt_version",
            "model",
            name="uq_llm_intelligence_run_input",
        ),
    )
    op.create_index(
        "ix_llm_intelligence_runs_task",
        "llm_intelligence_runs",
        ["task"],
    )
    op.create_index(
        "ix_llm_intelligence_runs_scope_kind",
        "llm_intelligence_runs",
        ["scope_kind"],
    )
    op.create_index(
        "ix_llm_intelligence_runs_scope_id",
        "llm_intelligence_runs",
        ["scope_id"],
    )
    op.create_index(
        "ix_llm_intelligence_runs_input_hash",
        "llm_intelligence_runs",
        ["input_hash"],
    )
    op.create_index(
        "ix_llm_intelligence_runs_status",
        "llm_intelligence_runs",
        ["status"],
    )
    op.create_index(
        "ix_llm_intelligence_runs_task_created",
        "llm_intelligence_runs",
        ["task", "created_at"],
    )
    op.add_column(
        "signals",
        sa.Column(
            "synthesis_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("signals", "synthesis_json")
    op.drop_index(
        "ix_llm_intelligence_runs_task_created",
        table_name="llm_intelligence_runs",
    )
    op.drop_index(
        "ix_llm_intelligence_runs_status",
        table_name="llm_intelligence_runs",
    )
    op.drop_index(
        "ix_llm_intelligence_runs_input_hash",
        table_name="llm_intelligence_runs",
    )
    op.drop_index(
        "ix_llm_intelligence_runs_scope_id",
        table_name="llm_intelligence_runs",
    )
    op.drop_index(
        "ix_llm_intelligence_runs_scope_kind",
        table_name="llm_intelligence_runs",
    )
    op.drop_index(
        "ix_llm_intelligence_runs_task",
        table_name="llm_intelligence_runs",
    )
    op.drop_table("llm_intelligence_runs")
