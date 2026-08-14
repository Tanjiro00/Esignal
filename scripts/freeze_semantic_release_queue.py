from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any

from packages.clustering.evidence_quality import (
    EvidenceReleasePolicy,
    assess_evidence_release,
)

SOURCE_ARTIFACT_SHA256 = "855196773f240b1024ba429ff804c2da284c336cad31f4b1204d6bb144a6a539"
PROTOCOL = "docs/evaluation/SEMANTIC_ADOPTION_RELEASE_QUEUE_V2_PROTOCOL_2026-08-13.md"


@dataclass(frozen=True)
class _EvidenceRow:
    video_id: str
    channel_id: str
    title: str
    upload_date: datetime


def _hash(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _date(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    source_sha = _hash(args.source)
    if source_sha != SOURCE_ARTIFACT_SHA256:
        raise ValueError(
            f"source artifact hash mismatch: expected {SOURCE_ARTIFACT_SHA256}, got {source_sha}"
        )
    root = Path(__file__).resolve().parents[1]
    protocol_path = root / PROTOCOL
    source = json.loads(args.source.read_text())
    policy = EvidenceReleasePolicy()
    rows: list[dict[str, Any]] = []
    for candidate in source["candidates"]:
        if not candidate["selected_top_quintile"]:
            continue
        evidence = tuple(
            _EvidenceRow(
                video_id=str(item["video_id"]),
                channel_id=str(item["channel_id"]),
                title=str(item["title"]),
                upload_date=_date(str(item["published_at"])),
            )
            for item in candidate["evidence"]
        )
        assessment = assess_evidence_release(evidence, policy=policy)
        rows.append(
            {
                "rank": candidate["rank"],
                "topic_key": candidate["topic_key"],
                "internal_rank_score": candidate["internal_rank_score"],
                "score_semantics": candidate["score_semantics"],
                "diagnostic_representative_title": candidate["diagnostic_representative_title"],
                "evidence_pre_audit": asdict(assessment),
                "agent_audit_status": (
                    "eligible_for_agent_audit"
                    if assessment.pre_audit_passed
                    else "abstain_deterministic_pre_audit"
                ),
                "required_agent_sequence": [
                    "evidence_analyst",
                    "trend_taxonomist",
                    "skeptic_auditor",
                    "creator_strategist_after_workspace_fit",
                ],
                "product_release_ready": False,
                "product_boundary": "shadow_only_no_act_no_probability",
                "evidence": candidate["evidence"],
            }
        )

    eligible = sum(row["agent_audit_status"] == "eligible_for_agent_audit" for row in rows)
    payload = {
        "artifact_version": "semantic-adoption-release-queue-v2",
        "frozen_at": datetime.now(tz=UTC).isoformat(),
        "status": "FROZEN_AWAITING_AGENT_AUDIT_AND_OUTCOMES",
        "source_artifact_sha256": source_sha,
        "source_checkpoint": source["candidate_checkpoint"],
        "source_outcome_embargo": source["outcomes_embargoed_until"],
        "protocol_sha256": _hash(protocol_path),
        "evidence_quality_source_sha256": _hash(root / "packages/clustering/evidence_quality.py"),
        "release_queue_script_sha256": _hash(root / "scripts/freeze_semantic_release_queue.py"),
        "release_policy": asdict(policy),
        "score_boundary": (
            "the source raw logit and rank are copied unchanged; evidence quality is a "
            "separate abstention layer"
        ),
        "candidate_count": len(rows),
        "eligible_for_agent_audit_count": eligible,
        "abstained_count": len(rows) - eligible,
        "candidates": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(
        json.dumps(
            {
                "status": payload["status"],
                "candidates": len(rows),
                "eligible_for_agent_audit": eligible,
                "abstained": len(rows) - eligible,
                "artifact_sha256": _hash(args.output),
                "protocol_sha256": payload["protocol_sha256"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
