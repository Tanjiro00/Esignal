"""slice 8 provider resilience

Revision ID: e84ad09c6721
Revises: c2d8f98b7c11
Create Date: 2026-07-27 17:20:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e84ad09c6721"
down_revision: str | None = "c2d8f98b7c11"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("provider_health") as batch_op:
        batch_op.add_column(
            sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0")
        )
        batch_op.add_column(
            sa.Column("circuit_opened_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("half_open_probe_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("manual_disabled_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("disabled_reason", sa.String(length=160), nullable=True)
        )

    with op.batch_alter_table("provider_budgets") as batch_op:
        batch_op.add_column(
            sa.Column("day_started_at", sa.DateTime(timezone=True), nullable=True)
        )
        batch_op.add_column(
            sa.Column("month_started_at", sa.DateTime(timezone=True), nullable=True)
        )
    op.execute(
        "UPDATE provider_budgets SET day_started_at = updated_at, "
        "month_started_at = updated_at "
        "WHERE day_started_at IS NULL OR month_started_at IS NULL"
    )
    with op.batch_alter_table("provider_budgets") as batch_op:
        batch_op.alter_column("day_started_at", nullable=False)
        batch_op.alter_column("month_started_at", nullable=False)

    op.create_table(
        "provider_routing_decisions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("capability", sa.String(length=40), nullable=False),
        sa.Column("operation_key", sa.String(length=180), nullable=False),
        sa.Column("selected_provider", sa.String(length=80), nullable=True),
        sa.Column("attempted_providers_json", sa.JSON(), nullable=False),
        sa.Column("skipped_providers_json", sa.JSON(), nullable=False),
        sa.Column("fallback_used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("reason", sa.String(length=160), nullable=False),
        sa.Column("estimated_cost", sa.Float(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_provider_routing_decisions_capability", ["capability"]),
        ("ix_provider_routing_decisions_operation_key", ["operation_key"]),
        ("ix_provider_routing_decisions_selected_provider", ["selected_provider"]),
        ("ix_provider_routing_decisions_fallback_used", ["fallback_used"]),
        ("ix_provider_routing_decisions_status", ["status"]),
    ):
        op.create_index(name, "provider_routing_decisions", columns)

    op.create_table(
        "provider_operations_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column("severity", sa.String(length=24), nullable=False),
        sa.Column("capability", sa.String(length=40), nullable=False),
        sa.Column("provider", sa.String(length=80), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("context_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_provider_operations_events_event_type", ["event_type"]),
        ("ix_provider_operations_events_severity", ["severity"]),
        ("ix_provider_operations_events_capability", ["capability"]),
        ("ix_provider_operations_events_provider", ["provider"]),
    ):
        op.create_index(name, "provider_operations_events", columns)

    op.create_table(
        "provider_benchmark_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("benchmark_version", sa.String(length=40), nullable=False),
        sa.Column("fixture_path", sa.String(length=500), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("live_case_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("recommended_priorities_json", sa.JSON(), nullable=False),
        sa.Column("json_path", sa.String(length=500), nullable=True),
        sa.Column("csv_path", sa.String(length=500), nullable=True),
        sa.Column("markdown_path", sa.String(length=500), nullable=True),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_provider_benchmark_runs_benchmark_version",
        "provider_benchmark_runs",
        ["benchmark_version"],
    )
    op.create_index(
        "ix_provider_benchmark_runs_status",
        "provider_benchmark_runs",
        ["status"],
    )


def downgrade() -> None:
    op.drop_index("ix_provider_benchmark_runs_status", table_name="provider_benchmark_runs")
    op.drop_index(
        "ix_provider_benchmark_runs_benchmark_version",
        table_name="provider_benchmark_runs",
    )
    op.drop_table("provider_benchmark_runs")

    for name in (
        "ix_provider_operations_events_provider",
        "ix_provider_operations_events_capability",
        "ix_provider_operations_events_severity",
        "ix_provider_operations_events_event_type",
    ):
        op.drop_index(name, table_name="provider_operations_events")
    op.drop_table("provider_operations_events")

    for name in (
        "ix_provider_routing_decisions_status",
        "ix_provider_routing_decisions_fallback_used",
        "ix_provider_routing_decisions_selected_provider",
        "ix_provider_routing_decisions_operation_key",
        "ix_provider_routing_decisions_capability",
    ):
        op.drop_index(name, table_name="provider_routing_decisions")
    op.drop_table("provider_routing_decisions")

    with op.batch_alter_table("provider_budgets") as batch_op:
        batch_op.drop_column("month_started_at")
        batch_op.drop_column("day_started_at")

    with op.batch_alter_table("provider_health") as batch_op:
        batch_op.drop_column("disabled_reason")
        batch_op.drop_column("manual_disabled_at")
        batch_op.drop_column("half_open_probe_at")
        batch_op.drop_column("circuit_opened_at")
        batch_op.drop_column("consecutive_failures")
