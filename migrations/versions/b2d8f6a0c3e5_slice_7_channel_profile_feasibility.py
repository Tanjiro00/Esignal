"""slice 7 channel profile v2 and production feasibility

Revision ID: b2d8f6a0c3e5
Revises: a1c7e5f9b2d4
Create Date: 2026-07-28 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2d8f6a0c3e5"
down_revision: str | None = "a1c7e5f9b2d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    columns = (
        sa.Column("core_topics_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column(
            "adjacent_topics_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "legacy_topics_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "successful_formats_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "upload_cadence_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "audience_sophistication",
            sa.String(length=24),
            nullable=False,
            server_default="intermediate",
        ),
        sa.Column(
            "creator_authority",
            sa.String(length=24),
            nullable=False,
            server_default="practitioner",
        ),
        sa.Column(
            "risk_tolerance",
            sa.String(length=24),
            nullable=False,
            server_default="balanced",
        ),
        sa.Column("team_size", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "research_capacity_hours",
            sa.Float(),
            nullable=False,
            server_default="8",
        ),
        sa.Column(
            "filming_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "external_guests_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "editing_complexity",
            sa.String(length=24),
            nullable=False,
            server_default="medium",
        ),
        sa.Column(
            "access_to_products_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "experiment_level",
            sa.String(length=24),
            nullable=False,
            server_default="balanced",
        ),
        sa.Column(
            "evergreen_trend_balance",
            sa.Float(),
            nullable=False,
            server_default="0.5",
        ),
        sa.Column(
            "weekday_publish_only",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "content_calendar_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "inference_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "explicit_overrides_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "profile_version",
            sa.String(length=48),
            nullable=False,
            server_default="channel-profile-v2",
        ),
    )
    for column in columns:
        op.add_column("channel_profiles", column)


def downgrade() -> None:
    for name in (
        "profile_version",
        "explicit_overrides_json",
        "inference_json",
        "content_calendar_json",
        "weekday_publish_only",
        "evergreen_trend_balance",
        "experiment_level",
        "access_to_products_json",
        "editing_complexity",
        "external_guests_required",
        "filming_required",
        "research_capacity_hours",
        "team_size",
        "risk_tolerance",
        "creator_authority",
        "audience_sophistication",
        "upload_cadence_json",
        "successful_formats_json",
        "legacy_topics_json",
        "adjacent_topics_json",
        "core_topics_json",
    ):
        op.drop_column("channel_profiles", name)
