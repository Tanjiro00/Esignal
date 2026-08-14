"""Regression guard for the raw/derived storage boundary."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
GUARDED_PACKAGES = ("packages/scoring", "packages/channel_fit", "packages/clustering")
FORBIDDEN_TOKENS = ("RawApiSnapshot", "raw_api_snapshots")


def test_scoring_does_not_read_raw() -> None:
    offenders: list[str] = []
    for package in GUARDED_PACKAGES:
        package_dir = REPO_ROOT / package
        assert package_dir.is_dir(), f"expected package directory at {package_dir}"
        for path in sorted(package_dir.rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            for token in FORBIDDEN_TOKENS:
                if token in source:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}: found {token!r}")
    assert not offenders, "raw mirror leaked into scoring-adjacent packages:\n" + "\n".join(
        offenders
    )
