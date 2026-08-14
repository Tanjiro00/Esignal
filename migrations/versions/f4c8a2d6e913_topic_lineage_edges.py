"""persist auditable topic lineage edges

Revision ID: f4c8a2d6e913
Revises: e3a6c8f1b927
Create Date: 2026-08-08 20:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f4c8a2d6e913"
down_revision: str | None = "e3a6c8f1b927"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "topic_lineage_edges",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_topic_id", sa.String(length=36), nullable=False),
        sa.Column("target_topic_id", sa.String(length=36), nullable=False),
        sa.Column("relationship", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("identity_fingerprint", sa.String(length=64), nullable=True),
        sa.Column("reason_codes_json", sa.JSON(), nullable=False),
        sa.Column("evidence_json", sa.JSON(), nullable=False),
        sa.Column("lineage_version", sa.String(length=48), nullable=False),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_topic_lineage_confidence",
        ),
        sa.CheckConstraint(
            "source_topic_id <> target_topic_id",
            name="ck_topic_lineage_distinct_topics",
        ),
        sa.CheckConstraint(
            "relationship IN ('successor', 'split_successor')",
            name="ck_topic_lineage_relationship",
        ),
        sa.ForeignKeyConstraint(["source_topic_id"], ["topics.id"]),
        sa.ForeignKeyConstraint(["target_topic_id"], ["topics.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_topic_id",
            "target_topic_id",
            "lineage_version",
            name="uq_topic_lineage_edge_version",
        ),
    )
    op.create_index(
        "ix_topic_lineage_edges_source_topic_id",
        "topic_lineage_edges",
        ["source_topic_id"],
        unique=False,
    )
    op.create_index(
        "ix_topic_lineage_edges_target_topic_id",
        "topic_lineage_edges",
        ["target_topic_id"],
        unique=False,
    )
    op.create_index(
        "ix_topic_lineage_edges_relationship",
        "topic_lineage_edges",
        ["relationship"],
        unique=False,
    )
    op.create_index(
        "ix_topic_lineage_edges_identity_fingerprint",
        "topic_lineage_edges",
        ["identity_fingerprint"],
        unique=False,
    )
    op.create_index(
        "ix_topic_lineage_edges_detected_at",
        "topic_lineage_edges",
        ["detected_at"],
        unique=False,
    )
    op.create_index(
        "ix_topic_lineage_source_detected",
        "topic_lineage_edges",
        ["source_topic_id", "detected_at"],
        unique=False,
    )
    op.create_index(
        "ix_topic_lineage_target_detected",
        "topic_lineage_edges",
        ["target_topic_id", "detected_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_topic_lineage_target_detected", table_name="topic_lineage_edges")
    op.drop_index("ix_topic_lineage_source_detected", table_name="topic_lineage_edges")
    op.drop_index("ix_topic_lineage_edges_detected_at", table_name="topic_lineage_edges")
    op.drop_index(
        "ix_topic_lineage_edges_identity_fingerprint",
        table_name="topic_lineage_edges",
    )
    op.drop_index("ix_topic_lineage_edges_relationship", table_name="topic_lineage_edges")
    op.drop_index("ix_topic_lineage_edges_target_topic_id", table_name="topic_lineage_edges")
    op.drop_index("ix_topic_lineage_edges_source_topic_id", table_name="topic_lineage_edges")
    op.drop_table("topic_lineage_edges")
