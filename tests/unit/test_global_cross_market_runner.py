from __future__ import annotations

from scripts.run_global_cross_market_backtest import _checkpoints, _gate


def test_train_and_holdout_checkpoints_are_temporally_separate() -> None:
    train = _checkpoints("train")
    holdout = _checkpoints("holdout")

    assert train[-1] < holdout[0]
    assert all((right - left).days == 7 for left, right in zip(train, train[1:], strict=False))


def test_holdout_without_positive_support_cannot_pass() -> None:
    ranking = {
        "predictions": 10,
        "fired": 10,
        "precision_at_10_percent": 100.0,
        "recall_percent": 100.0,
        "median_lead_days": 10.0,
    }
    metrics = {
        "fired_candidate_topics": 10,
        "candidate_base_rate_percent": 10.0,
        "rankings": {
            name: dict(ranking)
            for name in ("method", "supply", "countries", "velocity", "view_growth", "random")
        },
    }

    result = _gate(metrics, split="holdout")

    assert result["verdict"] == "INSUFFICIENT_OUTCOME_SUPPORT"
    assert result["checks"]["positive_outcome_support"] is False
