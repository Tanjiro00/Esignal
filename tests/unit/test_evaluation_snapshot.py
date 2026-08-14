import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from apps.api.models import Base
from apps.api.seed import seed_demo
from packages.evaluation import (
    FIXTURE_VERSION,
    build_evaluation_snapshot,
    verify_snapshot_content_hash,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_demo_evaluation_snapshot_is_deterministic_and_evidence_safe() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    captured_at = datetime(2026, 7, 28, 8, tzinfo=UTC)

    with Session(engine) as session:
        seed_demo(session)
        first = build_evaluation_snapshot(
            session,
            captured_at=captured_at,
            source_kind="demo",
            source_environment="test",
        )
        second = build_evaluation_snapshot(
            session,
            captured_at=captured_at,
            source_kind="demo",
            source_environment="test",
        )

    assert first == second
    assert first["fixture_version"] == FIXTURE_VERSION
    assert first["counts"]["topic_candidates"] == 5
    assert first["counts"]["visible_signals"] == 5
    assert first["privacy"] == {
        "comment_text_included": False,
        "commenter_hashes_included": False,
        "provider_payloads_included": False,
        "secrets_included": False,
    }
    assert verify_snapshot_content_hash(first)
    assert [topic["canonical_label"] for topic in first["topics"]] == sorted(
        topic["canonical_label"] for topic in first["topics"]
    )


def test_committed_evaluation_fixtures_match_the_slice_zero_contract() -> None:
    fixtures = (
        ("current-demo-snapshot.json", 5, 5, "demo"),
        ("current-production-snapshot.json", 10, 2, "live"),
    )
    for filename, topics, signals, source_kind in fixtures:
        payload = json.loads((REPOSITORY_ROOT / "fixtures" / "evaluation" / filename).read_text())
        assert payload["fixture_version"] == FIXTURE_VERSION
        assert payload["source_kind"] == source_kind
        assert payload["counts"]["topic_candidates"] == topics
        assert payload["counts"]["visible_signals"] == signals
        assert verify_snapshot_content_hash(payload)


def test_visual_baseline_manifest_resolves_to_unchanged_artifacts() -> None:
    manifest = json.loads(
        (REPOSITORY_ROOT / "fixtures" / "evaluation" / "baseline-screenshots.json").read_text()
    )

    assert manifest["fixture_version"] == "earlysignal-visual-baseline-v1"
    for screenshot in manifest["screenshots"]:
        image_path = REPOSITORY_ROOT / screenshot["path"]
        assert image_path.is_file()
        assert sha256(image_path.read_bytes()).hexdigest() == screenshot["sha256"]
