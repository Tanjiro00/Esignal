from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ProbabilityObservation:
    key: str
    probability: float
    label: bool


def _average_precision(rows: Sequence[ProbabilityObservation]) -> float:
    ordered = sorted(rows, key=lambda row: (-row.probability, row.key))
    positives = sum(row.label for row in ordered)
    if not positives:
        return 0.0
    correct = 0
    accumulated = 0.0
    for rank, row in enumerate(ordered, start=1):
        if row.label:
            correct += 1
            accumulated += correct / rank
    return accumulated / positives


def calculate_probability_metrics(
    observations: Sequence[ProbabilityObservation],
    *,
    top_k: int,
    calibration_bins: int = 10,
) -> dict[str, Any]:
    if top_k <= 0:
        raise ValueError("top_k must be positive")
    if calibration_bins <= 0:
        raise ValueError("calibration_bins must be positive")
    if not observations:
        return {
            "examples": 0,
            "positives": 0,
            "base_rate": None,
            "precision_at_k": None,
            "lift_at_k": None,
            "average_precision": None,
            "brier_score": None,
            "constant_brier_score": None,
            "expected_calibration_error": None,
        }
    ordered = sorted(observations, key=lambda row: (-row.probability, row.key))
    labels = [float(row.label) for row in ordered]
    probabilities = [min(1.0, max(0.0, row.probability)) for row in ordered]
    base_rate = sum(labels) / len(labels)
    selected = ordered[: min(top_k, len(ordered))]
    precision = sum(row.label for row in selected) / len(selected)
    brier = sum(
        (probability - label) ** 2 for probability, label in zip(probabilities, labels, strict=True)
    ) / len(labels)
    constant_brier = sum((base_rate - label) ** 2 for label in labels) / len(labels)
    calibration_error = 0.0
    for bin_index in range(calibration_bins):
        lower = bin_index / calibration_bins
        upper = (bin_index + 1) / calibration_bins
        members = [
            (probability, label)
            for probability, label in zip(probabilities, labels, strict=True)
            if lower <= probability < upper
            or (bin_index == calibration_bins - 1 and probability == 1)
        ]
        if not members:
            continue
        mean_probability = sum(item[0] for item in members) / len(members)
        mean_label = sum(item[1] for item in members) / len(members)
        calibration_error += len(members) / len(labels) * abs(mean_probability - mean_label)
    return {
        "examples": len(ordered),
        "positives": int(sum(labels)),
        "base_rate": round(base_rate, 6),
        "precision_at_k": round(precision, 6),
        "lift_at_k": round(precision / base_rate, 6) if base_rate else None,
        "average_precision": round(_average_precision(ordered), 6),
        "brier_score": round(brier, 6),
        "constant_brier_score": round(constant_brier, 6),
        "expected_calibration_error": round(calibration_error, 6),
        "log_loss": round(
            -sum(
                label * math.log(max(probability, 1e-9))
                + (1 - label) * math.log(max(1 - probability, 1e-9))
                for probability, label in zip(probabilities, labels, strict=True)
            )
            / len(labels),
            6,
        ),
    }


__all__ = ["ProbabilityObservation", "calculate_probability_metrics"]
