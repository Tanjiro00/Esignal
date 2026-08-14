"""Add workspace-scoped channel discovery plans.

Revision ID: 3e7a1c9d5b42
Revises: 1b7c9e4a5d62
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "3e7a1c9d5b42"
down_revision: str | None = "1b7c9e4a5d62"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workspace_discovery_queries",
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("query_id", sa.String(length=36), nullable=False),
        sa.Column("source_type", sa.String(length=48), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("evidence_refs_json", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["query_id"], ["discovery_queries.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("workspace_id", "query_id"),
    )
    op.create_index(
        "ix_workspace_discovery_queries_workspace_active",
        "workspace_discovery_queries",
        ["workspace_id", "active"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_workspace_discovery_queries_workspace_active",
        table_name="workspace_discovery_queries",
    )
    op.drop_table("workspace_discovery_queries")
