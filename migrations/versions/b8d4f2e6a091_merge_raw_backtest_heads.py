"""Merge the raw/derived-store and point-in-time backtest branches."""

from collections.abc import Sequence

revision: str = "b8d4f2e6a091"
down_revision: tuple[str, str] = ("9f1a4c6d2e83", "5c2f8a7d9e31")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
