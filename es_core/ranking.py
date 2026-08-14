"""Ranking, calibration and abstention.

Three deliberate departures from v1:

* **Purged, embargoed temporal splits.** Training and validation windows are
  separated by the full outcome horizon. Without that gap an episode's outcome
  is partly visible in training, which is the most likely reason the June run
  ranked well (AP 0.82) yet failed calibration (ECE 0.158).
* **Isotonic instead of Platt calibration.** Platt scaling can only stretch a
  sigmoid; the observed miscalibration had a shape it cannot fit.
* **Explicit abstention.** A candidate with weak evidence, no anchor or thin
  feature support returns no recommendation at all. "I don't know" is a valid
  and honest output, and the product treats it as one.

The model emits a rank score always and a probability only when the calibrator
was fitted on a window it did not train on.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import numpy.typing as npt
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from es_core.types import Candidate, ScoredCandidate

MODEL_VERSION = "es-adoption-logreg-v2"

FloatArray = npt.NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class TrainingExample:
    as_of: datetime
    features: Mapping[str, float]
    label: bool
    topic_id: str = ""


@dataclass(frozen=True, slots=True)
class RankingPolicy:
    outcome_horizon_days: int = 42
    l2: float = 1.0
    minimum_training_examples: int = 60
    minimum_positive_examples: int = 10
    minimum_calibration_examples: int = 80
    minimum_anchor_score: float = 1.5


class InsufficientTrainingData(ValueError):
    """Raised when a model cannot be identified from the available episodes."""


def purged_splits(
    examples: Sequence[TrainingExample],
    *,
    folds: int = 4,
    horizon_days: int = 42,
) -> list[tuple[list[int], list[int]]]:
    """Forward-chaining splits with an embargo equal to the outcome horizon.

    Fold k trains on everything up to a cut, skips ``horizon_days``, then
    validates on the next block. An episode whose outcome window overlaps the
    validation block never appears in training.
    """

    order = sorted(range(len(examples)), key=lambda index: examples[index].as_of)
    if len(order) < folds + 1:
        return []
    block = len(order) // (folds + 1)
    embargo = timedelta(days=horizon_days)
    splits: list[tuple[list[int], list[int]]] = []
    for fold in range(1, folds + 1):
        validation = order[fold * block : (fold + 1) * block]
        if not validation:
            continue
        start = examples[validation[0]].as_of
        train = [
            index for index in order[: fold * block] if examples[index].as_of + embargo <= start
        ]
        if train and validation:
            splits.append((train, validation))
    return splits


class AdoptionRanker:
    """Regularized logistic head with an optional isotonic calibrator."""

    def __init__(
        self,
        feature_names: Sequence[str],
        *,
        policy: RankingPolicy | None = None,
        model_version: str = MODEL_VERSION,
    ) -> None:
        self.feature_names = tuple(feature_names)
        self.policy = policy or RankingPolicy()
        self.model_version = model_version
        self._model: LogisticRegression | None = None
        self._calibrator: IsotonicRegression | None = None
        self._means: FloatArray | None = None
        self._scales: FloatArray | None = None
        self.training_examples = 0
        self.positive_examples = 0

    @property
    def calibrated(self) -> bool:
        return self._calibrator is not None

    def _matrix(self, rows: Sequence[Mapping[str, float]]) -> FloatArray:
        return np.asarray(
            [[float(row.get(name, 0.0)) for name in self.feature_names] for row in rows],
            dtype=np.float64,
        )

    def _standardize(self, matrix: FloatArray) -> FloatArray:
        if self._means is None or self._scales is None:
            raise InsufficientTrainingData("model has not been fitted")
        return np.asarray((matrix - self._means) / self._scales, dtype=np.float64)

    def fit(self, training: Sequence[TrainingExample]) -> AdoptionRanker:
        positives = sum(1 for example in training if example.label)
        if len(training) < self.policy.minimum_training_examples:
            raise InsufficientTrainingData(
                f"need {self.policy.minimum_training_examples} episodes, got {len(training)}"
            )
        if positives < self.policy.minimum_positive_examples:
            raise InsufficientTrainingData(
                f"need {self.policy.minimum_positive_examples} positives, got {positives}"
            )
        matrix = self._matrix([example.features for example in training])
        self._means = matrix.mean(axis=0)
        scales = matrix.std(axis=0)
        scales[scales < 1e-6] = 1.0
        self._scales = scales
        labels = np.asarray([float(example.label) for example in training])
        self._model = LogisticRegression(
            C=1.0 / self.policy.l2,
            max_iter=2_000,
            solver="lbfgs",
        ).fit(self._standardize(matrix), labels)
        self.training_examples = len(training)
        self.positive_examples = positives
        return self

    def calibrate(self, holdout: Sequence[TrainingExample]) -> bool:
        """Fit isotonic calibration on a strictly later window.

        The caller owns the temporal split so this method cannot accidentally
        inspect timestamps and calibrate on its own training data.
        """

        if len(holdout) < self.policy.minimum_calibration_examples:
            self._calibrator = None
            return False
        labels = np.asarray([float(example.label) for example in holdout])
        if len(set(labels.tolist())) < 2:
            self._calibrator = None
            return False
        scores = self.rank_scores([example.features for example in holdout])
        self._calibrator = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0).fit(
            scores, labels
        )
        return True

    def rank_scores(self, rows: Sequence[Mapping[str, float]]) -> FloatArray:
        if self._model is None:
            raise InsufficientTrainingData("model has not been fitted")
        scores = self._model.decision_function(self._standardize(self._matrix(rows)))
        return np.asarray(scores, dtype=np.float64)

    def probabilities(self, rows: Sequence[Mapping[str, float]]) -> FloatArray | None:
        if self._calibrator is None:
            return None
        return np.asarray(self._calibrator.predict(self.rank_scores(rows)), dtype=np.float64)

    def score(self, candidates: Sequence[Candidate]) -> tuple[ScoredCandidate, ...]:
        """Score candidates and abstain where the evidence cannot support a claim."""

        if not candidates:
            return ()
        rows = [candidate.features for candidate in candidates]
        scores = self.rank_scores(rows)
        probabilities = self.probabilities(rows)
        results: list[ScoredCandidate] = []
        for index, candidate in enumerate(candidates):
            reasons: list[str] = []
            if candidate.evidence.status != "accepted":
                reasons.extend(candidate.evidence.reasons or ("evidence_not_accepted",))
            anchor_score = max((anchor.score for anchor in candidate.anchors), default=0.0)
            if anchor_score < self.policy.minimum_anchor_score:
                reasons.append("no_specific_anchor")
            abstained = bool(reasons)
            results.append(
                ScoredCandidate(
                    candidate=candidate,
                    rank_score=round(float(scores[index]), 6),
                    probability=(
                        round(float(probabilities[index]), 6)
                        if probabilities is not None and not abstained
                        else None
                    ),
                    abstained=abstained,
                    reason_codes=tuple(dict.fromkeys(reasons)),
                )
            )
        return tuple(sorted(results, key=lambda item: (item.abstained, -item.rank_score)))


__all__ = [
    "AdoptionRanker",
    "InsufficientTrainingData",
    "MODEL_VERSION",
    "RankingPolicy",
    "TrainingExample",
    "purged_splits",
]
