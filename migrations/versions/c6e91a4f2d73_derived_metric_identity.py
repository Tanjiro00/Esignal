"""Make derived metric projection idempotent by its natural identity."""

from collections.abc import Sequence

from alembic import op

revision: str = "c6e91a4f2d73"
down_revision: str | None = "b8d4f2e6a091"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "uq_derived_metric_points_identity",
        "derived_metric_points",
        [
            "subject_type",
            "subject_id",
            "metric_name",
            "window",
            "scoring_version",
            "computed_at",
        ],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "uq_derived_metric_points_identity",
        table_name="derived_metric_points",
    )
