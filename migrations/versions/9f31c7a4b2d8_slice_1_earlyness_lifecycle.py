"""slice 1 earlyness and lifecycle history

Revision ID: 9f31c7a4b2d8
Revises: e52c91ab74d0
Create Date: 2026-07-28 12:20:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9f31c7a4b2d8"
down_revision: str | None = "e52c91ab74d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "topic_lifecycle_transitions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("topic_id", sa.String(length=36), nullable=False),
        sa.Column("from_stage", sa.String(length=32), nullable=True),
        sa.Column("to_stage", sa.String(length=32), nullable=False),
        sa.Column("transitioned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("measurement_id", sa.String(length=36), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("reason_codes_json", sa.JSON(), nullable=False),
        sa.Column("history_version", sa.String(length=48), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["measurement_id"], ["topic_snapshots.id"]),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "topic_id",
            "measurement_id",
            name="uq_topic_lifecycle_transition_measurement",
        ),
        sa.UniqueConstraint(
            "topic_id",
            "transitioned_at",
            "to_stage",
            name="uq_topic_lifecycle_transition_event",
        ),
    )
    op.create_index(
        "ix_topic_lifecycle_transitions_topic_id",
        "topic_lifecycle_transitions",
        ["topic_id"],
    )
    op.create_index(
        "ix_topic_lifecycle_transitions_to_stage",
        "topic_lifecycle_transitions",
        ["to_stage"],
    )
    op.create_index(
        "ix_topic_lifecycle_transitions_transitioned_at",
        "topic_lifecycle_transitions",
        ["transitioned_at"],
    )

    op.create_table(
        "topic_lifecycle_summaries",
        sa.Column("topic_id", sa.String(length=36), nullable=False),
        sa.Column("first_video_published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_discovered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_topic_formed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_seed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_emerging_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_signal_visible_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_breakout_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_mass_market_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_saturated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_declining_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "first_large_channel_adoption_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
        sa.Column("latest_measurement_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("backfill_version", sa.String(length=48), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"]),
        sa.PrimaryKeyConstraint("topic_id"),
    )


def downgrade() -> None:
    op.drop_table("topic_lifecycle_summaries")
    op.drop_index(
        "ix_topic_lifecycle_transitions_transitioned_at",
        table_name="topic_lifecycle_transitions",
    )
    op.drop_index(
        "ix_topic_lifecycle_transitions_to_stage",
        table_name="topic_lifecycle_transitions",
    )
    op.drop_index(
        "ix_topic_lifecycle_transitions_topic_id",
        table_name="topic_lifecycle_transitions",
    )
    op.drop_table("topic_lifecycle_transitions")
