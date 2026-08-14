"""stored demand items and comment embeddings

Demand items are what the product sells: a group of viewers asking the same
question that nothing answers. They are computed by a job and read by the API,
so they need to be persisted rather than recomputed per request.

Comment embeddings live here too. Questions and videos share one semantic
space, which is what lets "is there a video that answers this?" be a
nearest-neighbour lookup instead of a keyword search.

Revision ID: d5f8c1a3e764
Revises: c3a5b7e1d942
Create Date: 2026-08-15 09:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d5f8c1a3e764"
down_revision: str | None = "c3a5b7e1d942"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "comment_embeddings",
        sa.Column("comment_id", sa.String(length=36), nullable=False),
        sa.Column("embedding_version", sa.String(length=40), nullable=False),
        sa.Column("model_name", sa.String(length=80), nullable=False),
        sa.Column("dimensions", sa.Integer(), nullable=False),
        sa.Column("vector_json", sa.JSON(), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["comment_id"], ["youtube_comments.id"]),
        sa.PrimaryKeyConstraint("comment_id", "embedding_version"),
    )
    op.create_index(
        "ix_comment_embeddings_calculated",
        "comment_embeddings",
        ["calculated_at"],
        unique=False,
    )

    op.create_table(
        "demand_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("item_key", sa.String(length=32), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        # Neutral phrasing from the grounded verifier; empty until verified.
        sa.Column("need", sa.Text(), nullable=False, server_default=""),
        sa.Column("subject", sa.String(length=200), nullable=False, server_default=""),
        sa.Column("distinct_askers", sa.Integer(), nullable=False),
        sa.Column("distinct_videos", sa.Integer(), nullable=False),
        sa.Column("distinct_channels", sa.Integer(), nullable=False),
        sa.Column("total_likes", sa.Integer(), nullable=False),
        sa.Column("first_asked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_asked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("mean_similarity", sa.Float(), nullable=False),
        sa.Column("volume_score", sa.Float(), nullable=False),
        sa.Column("answered", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("answer_video_ids_json", sa.JSON(), nullable=False),
        sa.Column("anchors_json", sa.JSON(), nullable=False),
        sa.Column("centroid_json", sa.JSON(), nullable=False),
        sa.Column("verified", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("verifier_version", sa.String(length=40), nullable=True),
        sa.Column("pipeline_version", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    # One row per item per checkpoint; a rebuild replaces rather than duplicates.
    op.create_index(
        "ux_demand_items_key_asof",
        "demand_items",
        ["item_key", "as_of"],
        unique=True,
    )
    op.create_index(
        "ix_demand_items_ranking",
        "demand_items",
        ["as_of", "verified", "answered"],
        unique=False,
    )

    op.create_table(
        "demand_item_comments",
        sa.Column("demand_item_id", sa.String(length=36), nullable=False),
        sa.Column("comment_id", sa.String(length=36), nullable=False),
        sa.Column("is_evidence", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["demand_item_id"], ["demand_items.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["comment_id"], ["youtube_comments.id"]),
        sa.PrimaryKeyConstraint("demand_item_id", "comment_id"),
    )
    op.create_index(
        "ix_demand_item_comments_item",
        "demand_item_comments",
        ["demand_item_id", "position"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_demand_item_comments_item", table_name="demand_item_comments")
    op.drop_table("demand_item_comments")
    op.drop_index("ix_demand_items_ranking", table_name="demand_items")
    op.drop_index("ux_demand_items_key_asof", table_name="demand_items")
    op.drop_table("demand_items")
    op.drop_index("ix_comment_embeddings_calculated", table_name="comment_embeddings")
    op.drop_table("comment_embeddings")
