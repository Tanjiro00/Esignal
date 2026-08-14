"""slice 10 secure YouTube OAuth and owned analytics

Revision ID: e5a1c9d3f6b8
Revises: d4f0b8c2e5a7
Create Date: 2026-07-29 00:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5a1c9d3f6b8"
down_revision: str | None = "d4f0b8c2e5a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "youtube_oauth_connections",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("channel_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("scopes_json", sa.JSON(), nullable=False),
        sa.Column("encrypted_access_token", sa.Text(), nullable=False),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=False),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("token_encryption_version", sa.String(length=32), nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_refresh_error", sa.String(length=240), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["youtube_channels.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("workspace_id"),
    )
    op.create_index(
        "ix_youtube_oauth_connections_channel_id",
        "youtube_oauth_connections",
        ["channel_id"],
    )
    op.create_index(
        "ix_youtube_oauth_connections_status",
        "youtube_oauth_connections",
        ["status"],
    )

    op.create_table(
        "youtube_oauth_states",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("encrypted_code_verifier", sa.Text(), nullable=False),
        sa.Column("redirect_after", sa.String(length=500), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state_hash"),
    )
    op.create_index(
        "ix_youtube_oauth_states_workspace_id",
        "youtube_oauth_states",
        ["workspace_id"],
    )
    op.create_index(
        "ix_youtube_oauth_states_state_hash",
        "youtube_oauth_states",
        ["state_hash"],
    )
    op.create_index(
        "ix_youtube_oauth_states_expires_at",
        "youtube_oauth_states",
        ["expires_at"],
    )

    op.create_table(
        "youtube_owned_analytics",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("channel_id", sa.String(length=36), nullable=False),
        sa.Column("video_id", sa.String(length=36), nullable=True),
        sa.Column("youtube_video_id", sa.String(length=32), nullable=False),
        sa.Column("period_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("period_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("views", sa.BigInteger(), nullable=False),
        sa.Column("watch_time_minutes", sa.Float(), nullable=False),
        sa.Column("average_view_duration_seconds", sa.Float(), nullable=False),
        sa.Column("average_percentage_viewed", sa.Float(), nullable=False),
        sa.Column("subscribers_gained", sa.Integer(), nullable=False),
        sa.Column("revenue", sa.Float(), nullable=True),
        sa.Column("traffic_source_groups_json", sa.JSON(), nullable=False),
        sa.Column("geography_json", sa.JSON(), nullable=False),
        sa.Column("content_type", sa.String(length=24), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("analytics_version", sa.String(length=48), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["channel_id"], ["youtube_channels.id"]),
        sa.ForeignKeyConstraint(["video_id"], ["youtube_videos.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workspace_id",
            "youtube_video_id",
            "period_start",
            "period_end",
            "analytics_version",
            name="uq_owned_analytics_video_period_version",
        ),
    )
    op.create_index(
        "ix_youtube_owned_analytics_workspace_id",
        "youtube_owned_analytics",
        ["workspace_id"],
    )
    op.create_index(
        "ix_youtube_owned_analytics_channel_id",
        "youtube_owned_analytics",
        ["channel_id"],
    )
    op.create_index(
        "ix_youtube_owned_analytics_video_id",
        "youtube_owned_analytics",
        ["video_id"],
    )
    op.create_index(
        "ix_youtube_owned_analytics_youtube_video_id",
        "youtube_owned_analytics",
        ["youtube_video_id"],
    )
    op.create_index(
        "ix_youtube_owned_analytics_period_end",
        "youtube_owned_analytics",
        ["period_end"],
    )
    op.create_index(
        "ix_youtube_owned_analytics_observed_at",
        "youtube_owned_analytics",
        ["observed_at"],
    )
    op.create_index(
        "ix_owned_analytics_workspace_video_period",
        "youtube_owned_analytics",
        ["workspace_id", "youtube_video_id", "period_end"],
    )

    op.create_table(
        "youtube_oauth_audit_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=48), nullable=False),
        sa.Column("result", sa.String(length=24), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_youtube_oauth_audit_events_workspace_id",
        "youtube_oauth_audit_events",
        ["workspace_id"],
    )
    op.create_index(
        "ix_youtube_oauth_audit_events_event_type",
        "youtube_oauth_audit_events",
        ["event_type"],
    )
    op.create_index(
        "ix_youtube_oauth_audit_workspace_created",
        "youtube_oauth_audit_events",
        ["workspace_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_youtube_oauth_audit_workspace_created",
        table_name="youtube_oauth_audit_events",
    )
    op.drop_index(
        "ix_youtube_oauth_audit_events_event_type",
        table_name="youtube_oauth_audit_events",
    )
    op.drop_index(
        "ix_youtube_oauth_audit_events_workspace_id",
        table_name="youtube_oauth_audit_events",
    )
    op.drop_table("youtube_oauth_audit_events")
    op.drop_index(
        "ix_owned_analytics_workspace_video_period",
        table_name="youtube_owned_analytics",
    )
    op.drop_index(
        "ix_youtube_owned_analytics_observed_at",
        table_name="youtube_owned_analytics",
    )
    op.drop_index(
        "ix_youtube_owned_analytics_period_end",
        table_name="youtube_owned_analytics",
    )
    op.drop_index(
        "ix_youtube_owned_analytics_youtube_video_id",
        table_name="youtube_owned_analytics",
    )
    op.drop_index(
        "ix_youtube_owned_analytics_video_id",
        table_name="youtube_owned_analytics",
    )
    op.drop_index(
        "ix_youtube_owned_analytics_channel_id",
        table_name="youtube_owned_analytics",
    )
    op.drop_index(
        "ix_youtube_owned_analytics_workspace_id",
        table_name="youtube_owned_analytics",
    )
    op.drop_table("youtube_owned_analytics")
    op.drop_index(
        "ix_youtube_oauth_states_expires_at",
        table_name="youtube_oauth_states",
    )
    op.drop_index(
        "ix_youtube_oauth_states_state_hash",
        table_name="youtube_oauth_states",
    )
    op.drop_index(
        "ix_youtube_oauth_states_workspace_id",
        table_name="youtube_oauth_states",
    )
    op.drop_table("youtube_oauth_states")
    op.drop_index(
        "ix_youtube_oauth_connections_status",
        table_name="youtube_oauth_connections",
    )
    op.drop_index(
        "ix_youtube_oauth_connections_channel_id",
        table_name="youtube_oauth_connections",
    )
    op.drop_table("youtube_oauth_connections")
