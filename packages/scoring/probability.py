from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

PROBABILITY_MODEL_VERSION = "earlysignal-probability-head-v1"


class InsufficientTrainingData(ValueError):
    """Raised when a probability model cannot be identified from the training set."""


def _sigmoid(value: float) -> float:
    if value >= 0:
        return 1 / (1 + math.exp(-min(value, 40)))
    exponential = math.exp(max(value, -40))
    return exponential / (1 + exponential)


def _bounded_probability(value: float) -> float:
    return min(1 - 1e-9, max(1e-9, value))


@dataclass(frozen=True)
class ProbabilityTrainingExample:
    features: Mapping[str, float]
    label: bool


@dataclass(frozen=True)
class LogisticProbabilityModel:
    feature_names: tuple[str, ...]
    means: tuple[float, ...]
    scales: tuple[float, ...]
    coefficients: tuple[float, ...]
    intercept: float
    calibration_slope: float
    calibration_intercept: float
    calibrated: bool
    training_examples: int
    positive_examples: int
    model_version: str = PROBABILITY_MODEL_VERSION

    def _standardized(self, features: Mapping[str, float]) -> tuple[float, ...]:
        return tuple(
            (float(features.get(name, 0.0)) - mean) / scale
            for name, mean, scale in zip(
                self.feature_names,
                self.means,
                self.scales,
                strict=True,
            )
        )

    def raw_logit(self, features: Mapping[str, float]) -> float:
        values = self._standardized(features)
        return self.intercept + sum(
            coefficient * value
            for coefficient, value in zip(self.coefficients, values, strict=True)
        )

    def predict(self, features: Mapping[str, float]) -> float:
        raw = self.raw_logit(features)
        calibrated_logit = self.calibration_slope * raw + self.calibration_intercept
        return round(_sigmoid(calibrated_logit), 6)

    def payload(self) -> dict[str, Any]:
        return {
            "model_version": self.model_version,
            "feature_names": list(self.feature_names),
            "means": list(self.means),
            "scales": list(self.scales),
            "coefficients": list(self.coefficients),
            "intercept": self.intercept,
            "calibration_slope": self.calibration_slope,
            "calibration_intercept": self.calibration_intercept,
            "calibrated": self.calibrated,
            "training_examples": self.training_examples,
            "positive_examples": self.positive_examples,
        }


def _feature_schema(
    examples: Sequence[ProbabilityTrainingExample],
) -> tuple[str, ...]:
    names = tuple(sorted({name for example in examples for name in example.features}))
    if not names:
        raise InsufficientTrainingData("at least one feature is required")
    return names


def _matrix(
    examples: Sequence[ProbabilityTrainingExample],
    names: tuple[str, ...],
    *,
    means: tuple[float, ...] | None = None,
    scales: tuple[float, ...] | None = None,
) -> tuple[list[tuple[float, ...]], tuple[float, ...], tuple[float, ...]]:
    raw = [tuple(float(example.features.get(name, 0.0)) for name in names) for example in examples]
    if means is None:
        means = tuple(sum(row[index] for row in raw) / len(raw) for index in range(len(names)))
    if scales is None:
        scales = tuple(
            max(
                math.sqrt(sum((row[index] - means[index]) ** 2 for row in raw) / len(raw)),
                1e-6,
            )
            for index in range(len(names))
        )
    standardized = [
        tuple((value - mean) / scale for value, mean, scale in zip(row, means, scales, strict=True))
        for row in raw
    ]
    return standardized, means, scales


def _fit_logistic_parameters(
    matrix: Sequence[tuple[float, ...]],
    labels: Sequence[float],
    *,
    l2: float,
    steps: int,
    learning_rate: float,
) -> tuple[tuple[float, ...], float]:
    positive_rate = _bounded_probability(sum(labels) / len(labels))
    intercept = math.log(positive_rate / (1 - positive_rate))
    coefficients = [0.0] * len(matrix[0])
    for step in range(steps):
        coefficient_gradients = [0.0] * len(coefficients)
        intercept_gradient = 0.0
        for row, label in zip(matrix, labels, strict=True):
            logit = intercept + sum(
                coefficient * value for coefficient, value in zip(coefficients, row, strict=True)
            )
            error = _sigmoid(logit) - label
            intercept_gradient += error
            for index, value in enumerate(row):
                coefficient_gradients[index] += error * value
        rate = learning_rate / math.sqrt(1 + step / 100)
        sample_count = len(matrix)
        intercept -= rate * intercept_gradient / sample_count
        for index in range(len(coefficients)):
            gradient = coefficient_gradients[index] / sample_count + l2 * coefficients[index]
            coefficients[index] -= rate * gradient
    return tuple(round(value, 10) for value in coefficients), round(intercept, 10)


def _fit_platt_calibration(
    logits: Sequence[float],
    labels: Sequence[float],
) -> tuple[float, float, bool]:
    if len(logits) < 20 or len(set(labels)) < 2:
        return 1.0, 0.0, False
    slope = 1.0
    intercept = 0.0
    for step in range(1_000):
        slope_gradient = 0.0
        intercept_gradient = 0.0
        for logit, label in zip(logits, labels, strict=True):
            error = _sigmoid(slope * logit + intercept) - label
            slope_gradient += error * logit
            intercept_gradient += error
        rate = 0.03 / math.sqrt(1 + step / 100)
        count = len(logits)
        # A small pull towards slope=1 prevents unstable calibration on short windows.
        slope -= rate * (slope_gradient / count + 0.01 * (slope - 1))
        intercept -= rate * intercept_gradient / count
        slope = min(5.0, max(0.05, slope))
    return round(slope, 10), round(intercept, 10), True


def fit_logistic_probability_model(
    training: Sequence[ProbabilityTrainingExample],
    *,
    calibration: Sequence[ProbabilityTrainingExample] = (),
    l2: float = 0.05,
    steps: int = 1_500,
    learning_rate: float = 0.08,
) -> LogisticProbabilityModel:
    """Fit a deterministic, serializable and optionally calibrated probability head.

    Calibration examples must be temporally later than the fitting examples. The
    caller owns that split so this low-level function cannot accidentally inspect
    timestamps or future outcomes.
    """

    if len(training) < 20:
        raise InsufficientTrainingData("at least 20 training examples are required")
    labels = [float(example.label) for example in training]
    if len(set(labels)) < 2:
        raise InsufficientTrainingData("training examples must contain both outcomes")
    names = _feature_schema(training)
    matrix, means, scales = _matrix(training, names)
    coefficients, intercept = _fit_logistic_parameters(
        matrix,
        labels,
        l2=l2,
        steps=steps,
        learning_rate=learning_rate,
    )
    provisional = LogisticProbabilityModel(
        feature_names=names,
        means=means,
        scales=scales,
        coefficients=coefficients,
        intercept=intercept,
        calibration_slope=1.0,
        calibration_intercept=0.0,
        calibrated=False,
        training_examples=len(training),
        positive_examples=sum(example.label for example in training),
    )
    calibration_rows = [
        example
        for example in calibration
        if set(example.features).issubset(set(names)) or set(names).issubset(example.features)
    ]
    logits = [provisional.raw_logit(example.features) for example in calibration_rows]
    calibration_labels = [float(example.label) for example in calibration_rows]
    slope, calibration_intercept, calibrated = _fit_platt_calibration(
        logits,
        calibration_labels,
    )
    return LogisticProbabilityModel(
        feature_names=names,
        means=tuple(round(value, 10) for value in means),
        scales=tuple(round(value, 10) for value in scales),
        coefficients=coefficients,
        intercept=intercept,
        calibration_slope=slope,
        calibration_intercept=calibration_intercept,
        calibrated=calibrated,
        training_examples=len(training),
        positive_examples=sum(example.label for example in training),
    )


__all__ = [
    "InsufficientTrainingData",
    "LogisticProbabilityModel",
    "PROBABILITY_MODEL_VERSION",
    "ProbabilityTrainingExample",
    "fit_logistic_probability_model",
]
