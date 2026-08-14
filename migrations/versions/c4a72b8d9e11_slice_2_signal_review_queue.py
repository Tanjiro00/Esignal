"""slice 2 signal review queue

Revision ID: c4a72b8d9e11
Revises: 9f31c7a4b2d8
Create Date: 2026-07-28 12:35:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c4a72b8d9e11"
down_revision: str | None = "9f31c7a4b2d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "signal_reviews",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("signal_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("reviewer_id", sa.String(length=36), nullable=True),
        sa.Column("primary_reason", sa.String(length=48), nullable=True),
        sa.Column("reason_codes_json", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("thesis_override", sa.Text(), nullable=True),
        sa.Column("opportunity_override_json", sa.JSON(), nullable=False),
        sa.Column("evidence_selection_json", sa.JSON(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("first_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("review_version", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["signal_id"], ["signals.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "signal_id"),
    )
    op.create_index(
        "ix_signal_reviews_signal_id",
        "signal_reviews",
        ["signal_id"],
    )
    op.create_index(
        "ix_signal_reviews_status",
        "signal_reviews",
        ["status"],
    )
    op.create_index(
        "ix_signal_reviews_workspace_id",
        "signal_reviews",
        ["workspace_id"],
    )
    op.create_index(
        "ix_signal_reviews_workspace_status",
        "signal_reviews",
        ["workspace_id", "status"],
    )

    op.create_table(
        "signal_review_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("review_id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("signal_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("from_status", sa.String(length=24), nullable=True),
        sa.Column("to_status", sa.String(length=24), nullable=False),
        sa.Column("reviewer_id", sa.String(length=36), nullable=True),
        sa.Column("reason_codes_json", sa.JSON(), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("changes_json", sa.JSON(), nullable=False),
        sa.Column("provenance_json", sa.JSON(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["review_id"], ["signal_reviews.id"]),
        sa.ForeignKeyConstraint(["reviewer_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["signal_id"], ["signals.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_signal_review_events_event_type",
        "signal_review_events",
        ["event_type"],
    )
    op.create_index(
        "ix_signal_review_events_idempotency_key",
        "signal_review_events",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_signal_review_events_review_created",
        "signal_review_events",
        ["review_id", "created_at"],
    )
    op.create_index(
        "ix_signal_review_events_review_id",
        "signal_review_events",
        ["review_id"],
    )
    op.create_index(
        "ix_signal_review_events_signal_id",
        "signal_review_events",
        ["signal_id"],
    )
    op.create_index(
        "ix_signal_review_events_workspace_id",
        "signal_review_events",
        ["workspace_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_signal_review_events_workspace_id",
        table_name="signal_review_events",
    )
    op.drop_index(
        "ix_signal_review_events_signal_id",
        table_name="signal_review_events",
    )
    op.drop_index(
        "ix_signal_review_events_review_id",
        table_name="signal_review_events",
    )
    op.drop_index(
        "ix_signal_review_events_review_created",
        table_name="signal_review_events",
    )
    op.drop_index(
        "ix_signal_review_events_idempotency_key",
        table_name="signal_review_events",
    )
    op.drop_index(
        "ix_signal_review_events_event_type",
        table_name="signal_review_events",
    )
    op.drop_table("signal_review_events")
    op.drop_index(
        "ix_signal_reviews_workspace_status",
        table_name="signal_reviews",
    )
    op.drop_index("ix_signal_reviews_workspace_id", table_name="signal_reviews")
    op.drop_index("ix_signal_reviews_status", table_name="signal_reviews")
    op.drop_index("ix_signal_reviews_signal_id", table_name="signal_reviews")
    op.drop_table("signal_reviews")
