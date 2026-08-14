from datetime import UTC, datetime, timedelta

from packages.outcome_tracking import (
    MINIMUM_STABLE_COMPARABLE_SAMPLE,
    BaselineCandidate,
    BriefCandidate,
    SnapshotPoint,
    build_associated_metrics,
    build_comparable_baseline,
    match_upload_to_brief,
)

NOW = datetime(2026, 7, 28, 12, tzinfo=UTC)


def _video(
    video_id: str,
    *,
    title: str,
    days_ago: int,
    duration: int = 900,
    views_24h: int = 100_000,
) -> BaselineCandidate:
    return BaselineCandidate(
        video_id=video_id,
        title=title,
        description="Independent practical test.",
        published_at=NOW - timedelta(days=days_ago),
        duration_seconds=duration,
        is_short=False,
        is_live=False,
        snapshots=(
            SnapshotPoint(age_hours=24, views=views_24h),
            SnapshotPoint(age_hours=72, views=int(views_24h * 1.4)),
        ),
    )


def test_owned_upload_matches_specific_active_brief() -> None:
    result = match_upload_to_brief(
        upload_title="I tested Claude Code autonomous workflows end to end",
        upload_description="A practical agent workflow with failure cases.",
        published_at=NOW,
        candidates=(
            BriefCandidate(
                brief_id="brief-claude",
                signal_id="signal-claude",
                title="Claude Code autonomous workflows: the real test",
                evidence_text="Claude Code agent workflow practical test failure cases",
                created_at=NOW - timedelta(days=5),
            ),
            BriefCandidate(
                brief_id="brief-video",
                signal_id="signal-video",
                title="Local AI video generation benchmark",
                evidence_text="offline video models GPU workflow",
                created_at=NOW - timedelta(days=4),
            ),
        ),
    )

    assert result is not None
    assert result.brief_id == "brief-claude"
    assert result.confidence >= 0.4
    assert "title_overlap" in result.reason_codes


def test_comparable_baseline_excludes_short_live_and_bad_duration() -> None:
    target = _video(
        "target",
        title="Claude Code workflow test",
        days_ago=0,
        views_24h=180_000,
    )
    history = (
        _video("a", title="Claude Code agent workflow", days_ago=10, views_24h=90_000),
        _video("b", title="Claude Code setup workflow", days_ago=20, views_24h=110_000),
        _video("c", title="Coding agent benchmark", days_ago=30, views_24h=100_000),
        BaselineCandidate(
            **{
                **_video(
                    "short",
                    title="Claude Code workflow",
                    days_ago=8,
                    views_24h=900_000,
                ).__dict__,
                "is_short": True,
            }
        ),
        _video(
            "long",
            title="Claude Code workflow documentary",
            days_ago=9,
            duration=4_000,
            views_24h=800_000,
        ),
    )

    baseline = build_comparable_baseline(target=target, history=history)

    assert baseline["sample_size"] == 3
    assert baseline["sample_size_24h"] == 3
    assert baseline["minimum_stable_sample_size"] == MINIMUM_STABLE_COMPARABLE_SAMPLE
    assert baseline["stability"] == "early"
    assert baseline["stability_24h"] == "early"
    assert baseline["filters"]["upload_period_days"] == 180
    assert baseline["views_24h"] == 100_000
    assert "short" not in baseline["video_ids"]
    assert "long" not in baseline["video_ids"]


def test_comparable_baseline_is_stable_at_five_horizon_samples() -> None:
    target = _video(
        "target",
        title="Claude Code workflow test",
        days_ago=0,
    )
    history = tuple(
        _video(
            f"peer-{index}",
            title=f"Claude Code workflow test {index}",
            days_ago=index * 10,
            views_24h=80_000 + index * 10_000,
        )
        for index in range(1, 6)
    )

    baseline = build_comparable_baseline(target=target, history=history)

    assert baseline["sample_size"] == 5
    assert baseline["sample_size_24h"] == 5
    assert baseline["stability"] == "stable"
    assert baseline["stability_24h"] == "stable"


def test_comparable_baseline_does_not_broaden_beyond_six_months() -> None:
    target = _video("target", title="Local model test", days_ago=0)
    history = (
        _video("recent", title="Local model benchmark", days_ago=30),
        _video("old", title="Local model benchmark", days_ago=181),
    )

    baseline = build_comparable_baseline(target=target, history=history)

    assert baseline["sample_size"] == 1
    assert baseline["video_ids"] == ["recent"]
    assert baseline["stability"] == "early"


def test_metrics_use_associated_not_causal_language_and_delays() -> None:
    baseline = {
        "views_24h": 100_000,
        "sample_size": 5,
        "sample_size_24h": 5,
        "minimum_stable_sample_size": 5,
    }
    metrics = build_associated_metrics(
        target_snapshots=(SnapshotPoint(age_hours=24, views=150_000),),
        baseline=baseline,
        signal_detected_at=NOW - timedelta(days=8),
        brief_created_at=NOW - timedelta(days=5),
        published_at=NOW,
    )

    assert metrics["interpretation"] == "associated_uplift_not_causal"
    assert metrics["comparator"] == baseline
    assert metrics["channel_relative_uplift_24h"] == 1.5
    assert metrics["publish_delay_from_signal_hours"] == 192
    assert metrics["publish_delay_from_brief_hours"] == 120
