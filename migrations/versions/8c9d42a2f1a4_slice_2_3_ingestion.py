"""slice 2 and 3 ingestion operations

Revision ID: 8c9d42a2f1a4
Revises: 2fddfa08e7c5
Create Date: 2026-07-27 12:40:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8c9d42a2f1a4"
down_revision: str | None = "2fddfa08e7c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "workspace_channels",
        sa.Column("last_ingested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "workspace_channels",
        sa.Column("next_ingestion_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_workspace_channels_next_ingestion_at",
        "workspace_channels",
        ["next_ingestion_at"],
    )

    op.create_table(
        "discovery_queries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("query", sa.String(length=300), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("country", sa.String(length=8), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("source", sa.String(length=24), nullable=False),
        sa.Column("minimum_interval_seconds", sa.Integer(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("historical_yield", sa.Float(), nullable=False),
        sa.Column("cost_per_retained_video", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("query"),
    )
    op.create_index("ix_discovery_queries_query", "discovery_queries", ["query"])
    op.create_index("ix_discovery_queries_next_run_at", "discovery_queries", ["next_run_at"])

    op.create_table(
        "provider_budgets",
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("capability", sa.String(length=40), nullable=False),
        sa.Column("daily_limit_usd", sa.Float(), nullable=False),
        sa.Column("monthly_limit_usd", sa.Float(), nullable=False),
        sa.Column("spent_today_usd", sa.Float(), nullable=False),
        sa.Column("spent_month_usd", sa.Float(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("provider", "capability"),
    )

    op.create_table(
        "discovery_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("query_id", sa.String(length=36), nullable=True),
        sa.Column("channel_id", sa.String(length=36), nullable=True),
        sa.Column("provider", sa.String(length=80), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("unique_video_count", sa.Integer(), nullable=False),
        sa.Column("retained_video_count", sa.Integer(), nullable=False),
        sa.Column("estimated_cost", sa.Float(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["channel_id"], ["youtube_channels.id"]),
        sa.ForeignKeyConstraint(["query_id"], ["discovery_queries.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_discovery_runs_query_id", "discovery_runs", ["query_id"])
    op.create_index("ix_discovery_runs_channel_id", "discovery_runs", ["channel_id"])
    op.create_index("ix_discovery_runs_idempotency_key", "discovery_runs", ["idempotency_key"])

    op.create_table(
        "raw_payload_links",
        sa.Column("provider_fetch_id", sa.String(length=36), nullable=False),
        sa.Column("entity_type", sa.String(length=40), nullable=False),
        sa.Column("entity_id", sa.String(length=80), nullable=False),
        sa.ForeignKeyConstraint(["provider_fetch_id"], ["provider_fetches.id"]),
        sa.PrimaryKeyConstraint("provider_fetch_id", "entity_type", "entity_id"),
    )

    op.create_table(
        "video_discovery_occurrences",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("video_id", sa.String(length=36), nullable=False),
        sa.Column("query_id", sa.String(length=36), nullable=True),
        sa.Column("provider_fetch_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column("country", sa.String(length=8), nullable=False),
        sa.Column("language", sa.String(length=16), nullable=False),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["provider_fetch_id"], ["provider_fetches.id"]),
        sa.ForeignKeyConstraint(["query_id"], ["discovery_queries.id"]),
        sa.ForeignKeyConstraint(["video_id"], ["youtube_videos.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "video_id",
            "provider_fetch_id",
            "query_id",
            "position",
            name="uq_discovery_occurrence",
        ),
    )
    op.create_index(
        "ix_video_discovery_occurrences_discovered_at",
        "video_discovery_occurrences",
        ["discovered_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_video_discovery_occurrences_discovered_at",
        table_name="video_discovery_occurrences",
    )
    op.drop_table("video_discovery_occurrences")
    op.drop_table("raw_payload_links")
    op.drop_index("ix_discovery_runs_idempotency_key", table_name="discovery_runs")
    op.drop_index("ix_discovery_runs_channel_id", table_name="discovery_runs")
    op.drop_index("ix_discovery_runs_query_id", table_name="discovery_runs")
    op.drop_table("discovery_runs")
    op.drop_table("provider_budgets")
    op.drop_index("ix_discovery_queries_next_run_at", table_name="discovery_queries")
    op.drop_index("ix_discovery_queries_query", table_name="discovery_queries")
    op.drop_table("discovery_queries")
    op.drop_index(
        "ix_workspace_channels_next_ingestion_at",
        table_name="workspace_channels",
    )
    op.drop_column("workspace_channels", "next_ingestion_at")
    op.drop_column("workspace_channels", "last_ingested_at")
