from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from statistics import median
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session

from apps.api.models import (
    BacktestCheckpoint,
    BacktestOutcome,
    BacktestPrediction,
    BacktestReport,
)
from packages.backtest.harness import REPLAY_ALGORITHM_VERSION
from packages.backtest.labeler import OUTCOME_LABEL_VERSION

BACKTEST_REPORT_VERSION = "temporal-quality-report-v1"


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _percent(numerator: int, denominator: int) -> float:
    return round(numerator / denominator * 100, 1) if denominator else 0.0


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    return sha256(encoded).hexdigest()


@dataclass(frozen=True)
class QualityGatePolicy:
    top_k: int = 10
    minimum_checkpoints: int = 6
    minimum_precision_percent: float = 40
    minimum_median_lead_days: float = 21
    minimum_evaluation_coverage_percent: float = 80

    def __post_init__(self) -> None:
        if self.top_k <= 0:
            raise ValueError("top_k must be positive")
        if self.minimum_checkpoints <= 0:
            raise ValueError("minimum_checkpoints must be positive")
        for value in (
            self.minimum_precision_percent,
            self.minimum_evaluation_coverage_percent,
        ):
            if not 0 <= value <= 100:
                raise ValueError("percentage thresholds must be within 0..100")
        if self.minimum_median_lead_days < 0:
            raise ValueError("minimum_median_lead_days must be nonnegative")


def calculate_backtest_metrics(
    *,
    checkpoints: list[BacktestCheckpoint],
    predictions: list[BacktestPrediction],
    outcomes: list[BacktestOutcome],
    gate_policy: QualityGatePolicy | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    policy = gate_policy or QualityGatePolicy()
    checkpoint_ids = {checkpoint.id for checkpoint in checkpoints}
    checkpoint_times = {
        checkpoint.id: _aware(checkpoint.checkpoint_at) for checkpoint in checkpoints
    }
    selected_predictions = sorted(
        (
            row
            for row in predictions
            if row.checkpoint_id in checkpoint_ids and row.rank <= policy.top_k
        ),
        key=lambda row: (checkpoint_times[row.checkpoint_id], row.rank, row.candidate_key),
    )
    outcome_map = {
        (row.checkpoint_id, row.candidate_key): row
        for row in outcomes
        if row.checkpoint_id in checkpoint_ids
    }
    evaluated_predictions: list[tuple[BacktestPrediction, BacktestOutcome]] = []
    fired_predictions: list[tuple[BacktestPrediction, BacktestOutcome]] = []
    for prediction in selected_predictions:
        outcome = outcome_map.get((prediction.checkpoint_id, prediction.candidate_key))
        if outcome is None or outcome.status != "evaluated":
            continue
        evaluated_predictions.append((prediction, outcome))
        if outcome.fired:
            fired_predictions.append((prediction, outcome))

    all_evaluated_outcomes = [
        row for row in outcomes if row.checkpoint_id in checkpoint_ids and row.status == "evaluated"
    ]
    all_fired_outcomes = [row for row in all_evaluated_outcomes if row.fired]
    predicted_fired_keys = {
        (prediction.checkpoint_id, prediction.candidate_key)
        for prediction, outcome in fired_predictions
        if outcome.fired
    }
    lead_days = [
        round(
            (_aware(outcome.fired_at) - checkpoint_times[prediction.checkpoint_id]).total_seconds()
            / 86_400,
            2,
        )
        for prediction, outcome in fired_predictions
        if outcome.fired_at is not None
    ]
    precision = _percent(len(fired_predictions), len(evaluated_predictions))
    recall = _percent(len(predicted_fired_keys), len(all_fired_outcomes))
    evaluation_coverage = _percent(len(evaluated_predictions), len(selected_predictions))
    median_lead = round(float(median(lead_days)), 2) if lead_days else 0.0

    per_checkpoint: list[dict[str, Any]] = []
    for checkpoint in sorted(checkpoints, key=lambda item: _aware(item.checkpoint_at)):
        checkpoint_predictions = [
            row for row in selected_predictions if row.checkpoint_id == checkpoint.id
        ]
        evaluated = [
            (row, outcome_map[(row.checkpoint_id, row.candidate_key)])
            for row in checkpoint_predictions
            if (row.checkpoint_id, row.candidate_key) in outcome_map
            and outcome_map[(row.checkpoint_id, row.candidate_key)].status == "evaluated"
        ]
        fired = sum(outcome.fired for _, outcome in evaluated)
        per_checkpoint.append(
            {
                "checkpoint_at": _aware(checkpoint.checkpoint_at).isoformat(),
                "checkpoint_id": checkpoint.id,
                "evaluated_predictions": len(evaluated),
                "fired_predictions": fired,
                "precision_at_k_percent": _percent(fired, len(evaluated)),
                "predictions": len(checkpoint_predictions),
            }
        )

    metrics = {
        "all_evaluated_outcomes": len(all_evaluated_outcomes),
        "all_fired_outcomes": len(all_fired_outcomes),
        "checkpoint_count": len(checkpoints),
        "evaluated_predictions": len(evaluated_predictions),
        "evaluation_coverage_percent": evaluation_coverage,
        "fired_predictions": len(fired_predictions),
        "lead_time_days": {
            "maximum": round(max(lead_days), 2) if lead_days else 0.0,
            "median": median_lead,
            "minimum": round(min(lead_days), 2) if lead_days else 0.0,
            "samples": len(lead_days),
        },
        "per_checkpoint": per_checkpoint,
        "precision_at_k_percent": precision,
        "predictions_at_k": len(selected_predictions),
        "recall_percent": recall,
        "top_k": policy.top_k,
    }
    gate_checks: dict[str, dict[str, bool | float | int]] = {
        "checkpoint_count": {
            "actual": len(checkpoints),
            "passed": len(checkpoints) >= policy.minimum_checkpoints,
            "required": policy.minimum_checkpoints,
        },
        "evaluation_coverage_percent": {
            "actual": evaluation_coverage,
            "passed": evaluation_coverage >= policy.minimum_evaluation_coverage_percent,
            "required": policy.minimum_evaluation_coverage_percent,
        },
        "median_lead_time_days": {
            "actual": median_lead,
            "passed": bool(lead_days) and median_lead >= policy.minimum_median_lead_days,
            "required": policy.minimum_median_lead_days,
        },
        "precision_at_k_percent": {
            "actual": precision,
            "passed": bool(evaluated_predictions) and precision >= policy.minimum_precision_percent,
            "required": policy.minimum_precision_percent,
        },
    }
    gate = {
        "checks": gate_checks,
        "passed": all(check["passed"] for check in gate_checks.values()),
        "quality_gate_policy": {
            "minimum_checkpoints": policy.minimum_checkpoints,
            "minimum_evaluation_coverage_percent": (policy.minimum_evaluation_coverage_percent),
            "minimum_median_lead_days": policy.minimum_median_lead_days,
            "minimum_precision_percent": policy.minimum_precision_percent,
            "top_k": policy.top_k,
        },
    }
    return metrics, gate


def render_markdown_report(
    *,
    name: str,
    checkpoint_ids: list[str],
    metrics: dict[str, Any],
    gate: dict[str, Any],
) -> str:
    data_ready = bool(
        gate["checks"]["checkpoint_count"]["passed"]
        and gate["checks"]["evaluation_coverage_percent"]["passed"]
    )
    outcome = "PASS" if gate["passed"] else "FAIL" if data_ready else "INSUFFICIENT DATA"
    precision_display = (
        f"{metrics['precision_at_k_percent']}%"
        if metrics["evaluated_predictions"]
        else "N/A — no predictions have complete follow-up"
    )
    lead_display = (
        f"{metrics['lead_time_days']['median']} days"
        if metrics["lead_time_days"]["samples"]
        else "N/A — no fired outcomes with complete follow-up"
    )
    recall_display = (
        f"{metrics['recall_percent']}%"
        if metrics["all_fired_outcomes"]
        else "N/A — no fired outcomes are evaluable yet"
    )
    rows = [
        "# EarlySignal temporal backtest report",
        "",
        f"**Run:** {name}",
        f"**Quality gate:** {outcome}",
        f"**Checkpoint count:** {metrics['checkpoint_count']}",
        f"**Precision@{metrics['top_k']}:** {precision_display}",
        f"**Median lead time:** {lead_display}",
        f"**Recall:** {recall_display}",
        f"**Evaluated prediction coverage:** {metrics['evaluation_coverage_percent']}%",
        "",
        "## Gate checks",
        "",
        "| Check | Actual | Required | Result |",
        "|---|---:|---:|---|",
    ]
    for key, check in gate["checks"].items():
        actual = check["actual"] if data_ready else "N/A"
        result = "PASS" if check["passed"] else "FAIL" if data_ready else "PENDING"
        rows.append(f"| {key} | {actual} | {check['required']} | {result} |")
    rows.extend(
        [
            "",
            "## Checkpoints",
            "",
            *[f"- `{checkpoint_id}`" for checkpoint_id in checkpoint_ids],
            "",
            "## Method and limitations",
            "",
            "- Predictions use only the latest recorded topic snapshot at or before each cutoff.",
            (
                "- Outcome labels are computed blindly: the labeler never reads "
                "prediction ranks or scores."
            ),
            (
                "- A positive outcome requires supply growth ≥3x and median outlier "
                "lift ≥3 within the configured horizon."
            ),
            (
                "- A negative is evaluated only when follow-up evidence reaches the end "
                "of the horizon; incomplete histories are excluded."
            ),
            (
                "- The current replay reuses the score recorded by production at the "
                "historical timestamp. Full raw re-clustering remains a separate, stricter "
                "validation layer."
            ),
            "",
        ]
    )
    return "\n".join(rows)


class BacktestReportService:
    def __init__(self, session: Session) -> None:
        self._session = session

    def build_and_persist(
        self,
        *,
        name: str,
        checkpoints: list[BacktestCheckpoint],
        gate_policy: QualityGatePolicy | None = None,
    ) -> BacktestReport:
        if not checkpoints:
            raise ValueError("At least one checkpoint is required")
        checkpoint_ids = sorted(checkpoint.id for checkpoint in checkpoints)
        predictions = list(
            self._session.scalars(
                select(BacktestPrediction)
                .where(BacktestPrediction.checkpoint_id.in_(checkpoint_ids))
                .order_by(BacktestPrediction.checkpoint_id, BacktestPrediction.rank)
            )
        )
        outcomes = list(
            self._session.scalars(
                select(BacktestOutcome)
                .where(BacktestOutcome.checkpoint_id.in_(checkpoint_ids))
                .order_by(BacktestOutcome.checkpoint_id, BacktestOutcome.candidate_key)
            )
        )
        metrics, gate = calculate_backtest_metrics(
            checkpoints=checkpoints,
            predictions=predictions,
            outcomes=outcomes,
            gate_policy=gate_policy,
        )
        markdown = render_markdown_report(
            name=name,
            checkpoint_ids=checkpoint_ids,
            metrics=metrics,
            gate=gate,
        )
        payload = {
            "algorithm_version": REPLAY_ALGORITHM_VERSION,
            "checkpoint_ids": checkpoint_ids,
            "gate": gate,
            "label_version": OUTCOME_LABEL_VERSION,
            "markdown_report": markdown,
            "metrics": metrics,
            "name": name,
            "report_version": BACKTEST_REPORT_VERSION,
        }
        content_hash = _canonical_hash(payload)
        idempotency_key = f"backtest-report:{content_hash}"
        existing = self._session.scalar(
            select(BacktestReport).where(BacktestReport.idempotency_key == idempotency_key)
        )
        if existing is not None:
            return existing
        data_ready = bool(
            gate["checks"]["checkpoint_count"]["passed"]
            and gate["checks"]["evaluation_coverage_percent"]["passed"]
        )
        report = BacktestReport(
            id=str(uuid5(NAMESPACE_URL, f"earlysignal:{idempotency_key}")),
            idempotency_key=idempotency_key,
            name=name[:160],
            report_version=BACKTEST_REPORT_VERSION,
            algorithm_version=REPLAY_ALGORITHM_VERSION,
            label_version=OUTCOME_LABEL_VERSION,
            status="success" if data_ready else "insufficient_data",
            checkpoint_ids_json=checkpoint_ids,
            metrics_json=metrics,
            gate_json=gate,
            markdown_report=markdown,
            content_hash=content_hash,
            created_at=datetime.now(tz=UTC),
        )
        self._session.add(report)
        self._session.commit()
        return report


__all__ = [
    "BACKTEST_REPORT_VERSION",
    "BacktestReportService",
    "QualityGatePolicy",
    "calculate_backtest_metrics",
    "render_markdown_report",
]
