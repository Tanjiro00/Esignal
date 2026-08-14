from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from packages.backtest.modern_adoption import (
    load_structural_cohort,
    maximum_complete_checkpoint,
    weekly_checkpoints,
)
from packages.backtest.semantic_adoption import (
    QualityGatedSemanticCandidateBuilder,
    SemanticEpisode,
    SemanticReplayPolicy,
    SemanticTopicState,
    build_semantic_episodes,
    load_embedding_map,
)
from packages.clustering.evidence_quality import (
    COPY_RESISTANT_EVIDENCE_POLICY,
    EvidenceQualityPolicy,
    assess_evidence_quality,
)
from packages.scoring import ProbabilityTrainingExample, fit_logistic_probability_model

PROTOCOL = "SEMANTIC_ADOPTION_PROSPECTIVE_PROTOCOL_2026-08-13.md"
SOURCE_FILES = (
    "packages/backtest/semantic_adoption.py",
    "packages/clustering/evidence_quality.py",
    "packages/clustering/microtopics_v8.py",
    "packages/scoring/probability.py",
    "scripts/freeze_semantic_prospective_cohort.py",
)


def _date(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def _hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _training_example(episode: SemanticEpisode) -> ProbabilityTrainingExample:
    return ProbabilityTrainingExample(
        features=episode.features,
        label=episode.adoption_label,
    )


def _state_payload(state: SemanticTopicState) -> dict[str, Any]:
    payload = asdict(state)
    payload["observed_at"] = state.observed_at.isoformat()
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cohort", type=Path, required=True)
    parser.add_argument("--embeddings", type=Path, required=True)
    parser.add_argument("--checkpoint", type=_date, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    root = Path(__file__).resolve().parents[1]
    protocol_path = root / "docs" / "evaluation" / PROTOCOL
    videos = load_structural_cohort(args.cohort)
    embeddings = load_embedding_map(args.embeddings)
    policy = SemanticReplayPolicy()
    complete_through = maximum_complete_checkpoint(
        videos,
        outcome_horizon_days=policy.outcome_horizon_days,
    )
    training_checkpoints = weekly_checkpoints(
        datetime(2026, 3, 1, 23, 59, 59, tzinfo=UTC),
        datetime(2026, 6, 28, 23, 59, 59, tzinfo=UTC),
    )
    if training_checkpoints[-1] > complete_through:
        raise ValueError("historical training range does not have complete outcomes")
    if args.checkpoint <= training_checkpoints[-1]:
        raise ValueError("prospective checkpoint must be later than training outcomes")

    builder = QualityGatedSemanticCandidateBuilder(
        videos,
        embeddings,
        policy=policy,
        quality_policy=COPY_RESISTANT_EVIDENCE_POLICY,
    )
    training = build_semantic_episodes(builder, training_checkpoints)
    model = fit_logistic_probability_model([_training_example(row) for row in training])
    candidates = builder.states_at(args.checkpoint)
    video_by_id = {video.video_id: video for video in videos}
    strict_label_policy = EvidenceQualityPolicy()
    scored: list[tuple[float, SemanticTopicState, dict[str, Any]]] = []
    for state in candidates:
        members = tuple(video_by_id[video_id] for video_id in state.active_video_ids)
        assessment = assess_evidence_quality(members, policy=strict_label_policy)
        scored.append((model.raw_logit(state.probability_features()), state, asdict(assessment)))
    scored.sort(key=lambda row: (-row[0], row[1].topic_key))
    selected_count = math.ceil(len(scored) * 0.2) if scored else 0
    candidate_rows: list[dict[str, Any]] = []
    for rank, (rank_score, state, quality_payload) in enumerate(scored, start=1):
        evidence = [
            {
                "video_id": video_id,
                "channel_id": video_by_id[video_id].channel_id,
                "published_at": video_by_id[video_id].upload_date.isoformat(),
                "title": title,
                "url": f"https://www.youtube.com/watch?v={video_id}",
            }
            for video_id, title in zip(
                state.evidence_video_ids,
                state.evidence_titles,
                strict=True,
            )
        ]
        neutral_label = quality_payload["dominant_identity_label"]
        label_status = (
            "deterministic_anchor_supported"
            if quality_payload["accepted"] and neutral_label
            else "requires_evidence_grounded_taxonomist"
        )
        candidate_rows.append(
            {
                "rank": rank,
                "selected_top_quintile": rank <= selected_count,
                "topic_key": state.topic_key,
                "internal_rank_score": round(rank_score, 10),
                "score_semantics": "uncalibrated_raw_logit_not_a_probability",
                "neutral_label": neutral_label if label_status.endswith("supported") else None,
                "label_status": label_status,
                "diagnostic_representative_title": state.label,
                "features": state.probability_features(),
                "quality": quality_payload,
                "evidence": evidence,
                "state": _state_payload(state),
            }
        )

    source_hashes = {name: _hash(root / name) for name in SOURCE_FILES}
    payload = {
        "artifact_version": "semantic-adoption-prospective-shadow-v1",
        "frozen_at": datetime.now(tz=UTC).isoformat(),
        "candidate_checkpoint": args.checkpoint.isoformat(),
        "outcomes_embargoed_until": "2026-09-24T00:00:00+00:00",
        "status": "FROZEN_AWAITING_OUTCOMES",
        "selection_bias": "current-monitoring-universe-prospective-outcomes",
        "product_boundary": "shadow-only-no-act-no-user-probability",
        "cohort_sha256": _hash(args.cohort),
        "embeddings_sha256": _hash(args.embeddings),
        "protocol_sha256": _hash(protocol_path),
        "source_sha256": source_hashes,
        "policy": asdict(policy),
        "quality_policy": asdict(COPY_RESISTANT_EVIDENCE_POLICY),
        "training_range": [
            training_checkpoints[0].isoformat(),
            training_checkpoints[-1].isoformat(),
        ],
        "training_episode_count": len(training),
        "training_positive_count": sum(row.adoption_label for row in training),
        "model": model.payload(),
        "model_output_boundary": "raw ranking only; calibration and probabilities prohibited",
        "candidate_count": len(candidate_rows),
        "selected_count": selected_count,
        "candidates": candidate_rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "status": payload["status"],
                "candidate_checkpoint": payload["candidate_checkpoint"],
                "outcomes_embargoed_until": payload["outcomes_embargoed_until"],
                "training_episodes": payload["training_episode_count"],
                "training_positives": payload["training_positive_count"],
                "candidates": payload["candidate_count"],
                "selected": payload["selected_count"],
                "artifact_sha256": _hash(args.output),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
