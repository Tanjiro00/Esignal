from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from es_ingest.panel import (
    ChannelEvidence,
    CrawlPolicy,
    Membership,
    PanelRules,
    admits,
    apply_changes,
    coverage,
    expels,
    members_at,
    plan_crawl,
    reconcile,
)

NOW = datetime(2026, 8, 14, tzinfo=UTC)


def evidence(
    channel_id: str,
    *,
    uploads: int = 6,
    niche: float = 0.8,
    last_upload_days: float = 3,
    template: float = 0.0,
    observed_at: datetime | None = None,
) -> ChannelEvidence:
    return ChannelEvidence(
        channel_id=channel_id,
        observed_at=observed_at or NOW,
        uploads_in_window=uploads,
        niche_share=niche,
        last_upload_at=NOW - timedelta(days=last_upload_days),
        template_share=template,
    )


def test_admission_needs_activity_and_subject_and_originality() -> None:
    assert admits(evidence("good"))
    assert not admits(evidence("quiet", uploads=1))
    assert not admits(evidence("off_topic", niche=0.2))
    assert not admits(evidence("farm", template=0.95))


def test_leaving_is_easier_than_joining_so_membership_does_not_churn() -> None:
    """A channel drifting to 0.4 niche share stays; at 0.2 it leaves."""

    drifting = evidence("drifting", niche=0.40)

    assert not admits(drifting)
    assert expels(drifting, as_of=NOW) is None
    assert expels(evidence("gone", niche=0.20), as_of=NOW) == "off_niche"
    assert expels(evidence("silent", last_upload_days=200), as_of=NOW) == "dormant"


def test_panel_is_reconstructable_on_any_past_date() -> None:
    """The property that makes an honest backtest possible."""

    memberships = [
        Membership("early", NOW - timedelta(days=100), "seed"),
        Membership("late", NOW - timedelta(days=10), "neighbourhood"),
        Membership(
            "departed",
            NOW - timedelta(days=100),
            "seed",
            left_at=NOW - timedelta(days=30),
            left_reason="dormant",
        ),
    ]

    assert members_at(memberships, NOW - timedelta(days=50)) == {"early", "departed"}
    assert members_at(memberships, NOW) == {"early", "late"}


def test_reconcile_refuses_evidence_from_after_the_checkpoint() -> None:
    memberships = [Membership("a", NOW - timedelta(days=30), "seed")]
    future = evidence("b", observed_at=NOW + timedelta(days=1))

    with pytest.raises(ValueError, match="postdates"):
        reconcile(memberships, [future], as_of=NOW)


def test_reconcile_adds_and_removes_without_rewriting_history() -> None:
    memberships = [
        Membership("staying", NOW - timedelta(days=60), "seed"),
        Membership("leaving", NOW - timedelta(days=60), "seed"),
    ]
    changes = reconcile(
        memberships,
        [
            evidence("staying"),
            evidence("leaving", last_upload_days=300),
            evidence("joining"),
        ],
        as_of=NOW,
    )
    updated = apply_changes(memberships, changes)

    assert members_at(updated, NOW - timedelta(days=1)) == {"staying", "leaving"}
    assert members_at(updated, NOW + timedelta(seconds=1)) == {"staying", "joining"}
    # The departed row keeps its original join date rather than disappearing.
    departed = next(item for item in updated if item.channel_id == "leaving")
    assert departed.joined_at == NOW - timedelta(days=60)
    assert departed.left_reason == "dormant"


def test_never_polled_channels_are_crawled_before_recently_polled_ones() -> None:
    memberships = [
        Membership("fresh", NOW - timedelta(days=5), "seed"),
        Membership("old", NOW - timedelta(days=5), "seed"),
        Membership("never", NOW - timedelta(days=5), "seed"),
    ]
    last_polled = {
        "fresh": NOW - timedelta(hours=25),
        "old": NOW - timedelta(days=4),
    }

    plan = plan_crawl(memberships, last_polled, as_of=NOW)

    assert plan[0] == "never"
    assert plan.index("old") < plan.index("fresh")


def test_recently_polled_channels_are_skipped_and_capacity_is_respected() -> None:
    memberships = [Membership(f"c{index}", NOW - timedelta(days=5), "seed") for index in range(5)]
    last_polled = {"c0": NOW - timedelta(hours=1)}

    plan = plan_crawl(memberships, last_polled, as_of=NOW, policy=CrawlPolicy(daily_capacity=2))

    assert "c0" not in plan
    assert len(plan) == 2


def test_a_customer_channel_neighbourhood_is_polled_first() -> None:
    memberships = [
        Membership("core", NOW - timedelta(days=5), "seed"),
        Membership("customer", NOW - timedelta(days=5), "neighbourhood", owner_workspace_id="ws1"),
    ]

    plan = plan_crawl(memberships, {}, as_of=NOW)

    assert plan[0] == "customer"


def test_coverage_reports_the_share_polled_inside_the_window() -> None:
    memberships = [Membership(f"c{index}", NOW - timedelta(days=5), "seed") for index in range(4)]
    last_polled = {"c0": NOW - timedelta(hours=2), "c1": NOW - timedelta(hours=10)}

    assert coverage(memberships, last_polled, as_of=NOW) == 0.5


def test_rules_are_configurable_without_touching_the_logic() -> None:
    strict = PanelRules(minimum_recent_uploads=10, minimum_niche_share=0.9)

    assert admits(evidence("busy", uploads=12, niche=0.95), rules=strict)
    assert not admits(evidence("normal"), rules=strict)
