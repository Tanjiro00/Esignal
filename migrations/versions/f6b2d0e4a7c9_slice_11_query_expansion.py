"""slice 11 controlled query expansion and precision

Revision ID: f6b2d0e4a7c9
Revises: e5a1c9d3f6b8
Create Date: 2026-07-29 02:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f6b2d0e4a7c9"
down_revision: str | None = "e5a1c9d3f6b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "discovery_queries",
        sa.Column("precision_score", sa.Float(), nullable=False, server_default="0"),
    )
    op.add_column(
        "discovery_queries",
        sa.Column("precision_sample_size", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "discovery_queries",
        sa.Column(
            "quality_status",
            sa.String(length=24),
            nullable=False,
            server_default="unmeasured",
        ),
    )
    op.add_column(
        "discovery_queries",
        sa.Column("last_precision_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "query_suggestions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("query", sa.String(length=300), nullable=False),
        sa.Column("normalized_query", sa.String(length=300), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("source_type", sa.String(length=48), nullable=False),
        sa.Column("source_entity", sa.String(length=240), nullable=False),
        sa.Column("source_topic_id", sa.String(length=36), nullable=True),
        sa.Column("source_evidence_ids_json", sa.JSON(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("anchor_terms_json", sa.JSON(), nullable=False),
        sa.Column("quality_reason_codes_json", sa.JSON(), nullable=False),
        sa.Column("broadness_score", sa.Float(), nullable=False),
        sa.Column("precision_score", sa.Float(), nullable=False),
        sa.Column("precision_sample_size", sa.Integer(), nullable=False),
        sa.Column("discovery_query_id", sa.String(length=36), nullable=True),
        sa.Column("reviewed_by", sa.String(length=36), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("model_version", sa.String(length=48), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["discovery_query_id"], ["discovery_queries.id"]),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["source_topic_id"], ["topics.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "normalized_query",
            name="uq_query_suggestions_normalized",
        ),
    )
    op.create_index(
        "ix_query_suggestions_workspace_id",
        "query_suggestions",
        ["workspace_id"],
    )
    op.create_index(
        "ix_query_suggestions_normalized_query",
        "query_suggestions",
        ["normalized_query"],
    )
    op.create_index(
        "ix_query_suggestions_status",
        "query_suggestions",
        ["status"],
    )
    op.create_index(
        "ix_query_suggestions_source_type",
        "query_suggestions",
        ["source_type"],
    )
    op.create_index(
        "ix_query_suggestions_source_topic_id",
        "query_suggestions",
        ["source_topic_id"],
    )
    op.create_index(
        "ix_query_suggestions_discovery_query_id",
        "query_suggestions",
        ["discovery_query_id"],
    )
    op.create_index(
        "ix_query_suggestions_status_created",
        "query_suggestions",
        ["status", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_query_suggestions_status_created",
        table_name="query_suggestions",
    )
    op.drop_index(
        "ix_query_suggestions_discovery_query_id",
        table_name="query_suggestions",
    )
    op.drop_index(
        "ix_query_suggestions_source_topic_id",
        table_name="query_suggestions",
    )
    op.drop_index("ix_query_suggestions_source_type", table_name="query_suggestions")
    op.drop_index("ix_query_suggestions_status", table_name="query_suggestions")
    op.drop_index(
        "ix_query_suggestions_normalized_query",
        table_name="query_suggestions",
    )
    op.drop_index("ix_query_suggestions_workspace_id", table_name="query_suggestions")
    op.drop_table("query_suggestions")
    op.drop_column("discovery_queries", "last_precision_at")
    op.drop_column("discovery_queries", "quality_status")
    op.drop_column("discovery_queries", "precision_sample_size")
    op.drop_column("discovery_queries", "precision_score")
