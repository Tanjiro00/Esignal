"""slice 13 LLM evidence decision graph trace

Revision ID: 8d3f2a7b9c41
Revises: 6a9d1c4e8b27
Create Date: 2026-07-28 18:10:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "8d3f2a7b9c41"
down_revision: str | None = "6a9d1c4e8b27"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "topic_pipeline_runs",
        sa.Column(
            "llm_policy_version",
            sa.String(length=64),
            nullable=False,
            server_default="",
        ),
    )
    op.add_column(
        "topic_pipeline_runs",
        sa.Column(
            "llm_trace_json",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )


def downgrade() -> None:
    op.drop_column("topic_pipeline_runs", "llm_trace_json")
    op.drop_column("topic_pipeline_runs", "llm_policy_version")
