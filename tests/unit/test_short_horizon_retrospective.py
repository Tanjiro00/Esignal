from datetime import UTC, datetime, timedelta

import pytest

from packages.backtest.retrospective import (
    ShortHorizonObservation,
    ShortHorizonPolicy,
    label_short_horizon,
)

CHECKPOINT = datetime(2026, 8, 1, tzinfo=UTC)


def _observation(
    snapshot_id: str,
    *,
    days: float,
    supply: int,
    lift: float,
) -> ShortHorizonObservation:
    return ShortHorizonObservation(
        snapshot_id=snapshot_id,
        observed_at=CHECKPOINT + timedelta(days=days),
        supply_72h=supply,
        median_outlier_lift=lift,
    )


def test_short_horizon_requires_joint_supply_and_lift_crossing() -> None:
    label = label_short_horizon(
        baseline_supply_72h=2,
        checkpoint_at=CHECKPOINT,
        horizon_days=3,
        observations=[
            _observation("supply-only", days=1, supply=6, lift=2.9),
            _observation("lift-only", days=2.5, supply=5, lift=3.2),
        ],
    )

    assert label.status == "evaluated"
    assert label.fired is False
    assert label.supply_gate_reached is True
    assert label.lift_gate_reached is True
    assert label.best_joint_fraction_of_gate < 1


def test_short_horizon_records_first_joint_firing_snapshot() -> None:
    label = label_short_horizon(
        baseline_supply_72h=2,
        checkpoint_at=CHECKPOINT,
        horizon_days=5,
        observations=[
            _observation("before", days=1, supply=5, lift=4),
            _observation("first-hit", days=2, supply=6, lift=3),
            _observation("later-hit", days=3, supply=8, lift=5),
        ],
    )

    assert label.status == "evaluated"
    assert label.fired is True
    assert label.fired_snapshot_id == "first-hit"
    assert label.fired_at == CHECKPOINT + timedelta(days=2)
    assert label.best_joint_fraction_of_gate >= 1


def test_short_horizon_missing_end_coverage_is_not_a_negative() -> None:
    label = label_short_horizon(
        baseline_supply_72h=2,
        checkpoint_at=CHECKPOINT,
        horizon_days=1,
        observations=[_observation("early-only", days=0.2, supply=2, lift=1)],
    )

    assert label.status == "insufficient_evidence"
    assert label.fired is False


def test_short_horizon_ignores_observations_outside_window() -> None:
    label = label_short_horizon(
        baseline_supply_72h=2,
        checkpoint_at=CHECKPOINT,
        horizon_days=1,
        observations=[
            _observation("too-late", days=1.1, supply=20, lift=20),
        ],
    )

    assert label.status == "insufficient_evidence"
    assert label.followup_count == 0
    assert label.fired is False


def test_short_horizon_policy_rejects_unregistered_horizon() -> None:
    with pytest.raises(ValueError, match="registered"):
        ShortHorizonPolicy().grace_days(2)
