"""slice 10 private beta release

Revision ID: a8d4c1e29f60
Revises: f719ef52a8b3
Create Date: 2026-07-27 18:05:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a8d4c1e29f60"
down_revision: str | None = "f719ef52a8b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workspace_onboarding",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            nullable=False,
            server_default="in_progress",
        ),
        sa.Column("current_step", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("completed_steps_json", sa.JSON(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("workspace_id"),
    )
    op.create_index(
        "ix_workspace_onboarding_status",
        "workspace_onboarding",
        ["status"],
    )
    op.create_table(
        "product_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("event_key", sa.String(length=180), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=True),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("signal_id", sa.String(length=36), nullable=True),
        sa.Column("content_brief_id", sa.String(length=36), nullable=True),
        sa.Column("outcome_id", sa.String(length=36), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["content_brief_id"], ["content_briefs.id"]),
        sa.ForeignKeyConstraint(["outcome_id"], ["published_outcomes.id"]),
        sa.ForeignKeyConstraint(["signal_id"], ["signals.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_key"),
    )
    op.create_index("ix_product_events_event_key", "product_events", ["event_key"])
    op.create_index("ix_product_events_event_type", "product_events", ["event_type"])
    op.create_index("ix_product_events_occurred_at", "product_events", ["occurred_at"])
    op.create_index("ix_product_events_signal_id", "product_events", ["signal_id"])
    op.create_index("ix_product_events_workspace_id", "product_events", ["workspace_id"])
    op.create_table(
        "digest_subscriptions",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column(
            "cadence",
            sa.String(length=24),
            nullable=False,
            server_default="twice_weekly",
        ),
        sa.Column(
            "delivery_channel",
            sa.String(length=24),
            nullable=False,
            server_default="in_app",
        ),
        sa.Column("destination", sa.String(length=320), nullable=False, server_default=""),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("workspace_id"),
    )
    op.create_index(
        "ix_digest_subscriptions_next_run_at",
        "digest_subscriptions",
        ["next_run_at"],
    )
    op.create_table(
        "digest_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            nullable=False,
            server_default="generated",
        ),
        sa.Column("content_json", sa.JSON(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_digest_runs_generated_at", "digest_runs", ["generated_at"])
    op.create_index("ix_digest_runs_status", "digest_runs", ["status"])
    op.create_index("ix_digest_runs_workspace_id", "digest_runs", ["workspace_id"])


def downgrade() -> None:
    op.drop_index("ix_digest_runs_workspace_id", table_name="digest_runs")
    op.drop_index("ix_digest_runs_status", table_name="digest_runs")
    op.drop_index("ix_digest_runs_generated_at", table_name="digest_runs")
    op.drop_table("digest_runs")
    op.drop_index(
        "ix_digest_subscriptions_next_run_at",
        table_name="digest_subscriptions",
    )
    op.drop_table("digest_subscriptions")
    op.drop_index("ix_product_events_workspace_id", table_name="product_events")
    op.drop_index("ix_product_events_signal_id", table_name="product_events")
    op.drop_index("ix_product_events_occurred_at", table_name="product_events")
    op.drop_index("ix_product_events_event_type", table_name="product_events")
    op.drop_index("ix_product_events_event_key", table_name="product_events")
    op.drop_table("product_events")
    op.drop_index(
        "ix_workspace_onboarding_status",
        table_name="workspace_onboarding",
    )
    op.drop_table("workspace_onboarding")
