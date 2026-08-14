import pytest

from packages.evaluation import ProbabilityObservation, calculate_probability_metrics
from packages.scoring import (
    InsufficientTrainingData,
    ProbabilityTrainingExample,
    fit_logistic_probability_model,
)


def _example(value: float, label: bool) -> ProbabilityTrainingExample:
    return ProbabilityTrainingExample(features={"momentum": value}, label=label)


def test_probability_model_learns_direction_and_is_deterministic() -> None:
    training = [_example(index / 10, index >= 0) for index in range(-40, 40)]
    calibration = [_example(index / 10, index >= 0) for index in range(-20, 20)]

    first = fit_logistic_probability_model(training, calibration=calibration)
    second = fit_logistic_probability_model(training, calibration=calibration)

    assert first.payload() == second.payload()
    assert first.calibrated is True
    assert first.predict({"momentum": 3}) > 0.8
    assert first.predict({"momentum": -3}) < 0.2


def test_probability_model_rejects_one_class_training_data() -> None:
    with pytest.raises(InsufficientTrainingData, match="both outcomes"):
        fit_logistic_probability_model([_example(float(index), False) for index in range(20)])


def test_probability_metrics_report_lift_calibration_and_brier_baseline() -> None:
    metrics = calculate_probability_metrics(
        [
            ProbabilityObservation("a", 0.9, True),
            ProbabilityObservation("b", 0.8, True),
            ProbabilityObservation("c", 0.2, False),
            ProbabilityObservation("d", 0.1, False),
        ],
        top_k=2,
    )

    assert metrics["base_rate"] == 0.5
    assert metrics["precision_at_k"] == 1
    assert metrics["lift_at_k"] == 2
    assert metrics["average_precision"] == 1
    assert metrics["brier_score"] < metrics["constant_brier_score"]
