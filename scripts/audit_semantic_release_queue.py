from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any, cast

from apps.api.config import get_settings
from apps.api.database import SessionLocal
from apps.worker.llm_intelligence import LLM_POLICY_VERSION, LLMIntelligenceService
from packages.clustering.evidence_quality import (
    EvidenceQualityPolicy,
    EvidenceReleasePolicy,
    title_family_groups,
)
from packages.llm_intelligence import (
    EvidenceItem,
    ShadowEvidenceDossier,
    ShadowTrendAudit,
    ShadowTrendTaxonomy,
)

SOURCE_QUEUE_SHA256 = "19f2fded971a2f86a6ffae11567e2e2bfc9481f8ed03cee75b6d5b26d1e9d48f"


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


def _evidence_payload(
    candidate: dict[str, Any],
    release_policy: EvidenceReleasePolicy,
) -> tuple[list[EvidenceItem], dict[str, dict[str, str]]]:
    rows = tuple(
        _EvidenceRow(
            video_id=str(item["video_id"]),
            channel_id=str(item["channel_id"]),
            title=str(item["title"]),
            upload_date=_date(str(item["published_at"])),
        )
        for item in candidate["evidence"]
    )
    family_policy = EvidenceQualityPolicy(
        near_duplicate_jaccard=release_policy.near_duplicate_jaccard,
        near_duplicate_containment=release_policy.near_duplicate_containment,
        minimum_title_families=release_policy.minimum_title_families,
        minimum_concrete_identity_videos=0,
        minimum_concrete_identity_share=0,
    )
    family_by_video: dict[str, str] = {}
    for index, family in enumerate(title_family_groups(rows, policy=family_policy), start=1):
        family_id = f"family-{index}"
        for row in family:
            family_by_video[row.video_id] = family_id
    evidence = [
        EvidenceItem(
            ref=f"video:{row.video_id}",
            kind="video",
            title=row.title,
            text=(
                f"Stored YouTube title published at {row.upload_date.isoformat()}; "
                f"deterministic title family {family_by_video[row.video_id]}."
            ),
        )
        for row in rows
    ]
    metadata = {
        f"video:{row.video_id}": {
            "channel_id": row.channel_id,
            "title_family": family_by_video[row.video_id],
            "published_at": row.upload_date.isoformat(),
        }
        for row in rows
    }
    return evidence, metadata


def _result_payload(result: object) -> dict[str, object]:
    stored = cast(Any, result)
    return {
        "run_id": stored.run_id,
        "provider": stored.provider,
        "model": stored.model,
        "prompt_version": stored.prompt_version,
        "cached": stored.cached,
        "output": stored.value.model_dump(mode="json"),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=8)
    args = parser.parse_args()

    source_sha = _hash(args.source)
    if source_sha != SOURCE_QUEUE_SHA256:
        raise ValueError(
            f"source queue hash mismatch: expected {SOURCE_QUEUE_SHA256}, got {source_sha}"
        )
    source = json.loads(args.source.read_text())
    release_policy = EvidenceReleasePolicy(**source["release_policy"])
    settings = get_settings()
    settings.validate_runtime()
    processed = 0
    rows: list[dict[str, Any]] = []
    with SessionLocal() as session:
        service = LLMIntelligenceService(session, settings)
        for candidate in source["candidates"]:
            row = {
                "rank": candidate["rank"],
                "topic_key": candidate["topic_key"],
                "internal_rank_score": candidate["internal_rank_score"],
                "score_semantics": candidate["score_semantics"],
                "product_release_ready": False,
            }
            if candidate["agent_audit_status"] != "eligible_for_agent_audit":
                rows.append(
                    {
                        **row,
                        "shadow_audit_status": "abstained_deterministic_pre_audit",
                        "pre_audit": candidate["evidence_pre_audit"],
                    }
                )
                continue
            if processed >= max(0, args.limit):
                rows.append({**row, "shadow_audit_status": "not_processed_batch_limit"})
                continue
            processed += 1
            evidence, evidence_metadata = _evidence_payload(candidate, release_policy)
            trace_id = f"shadow-release-audit:{candidate['topic_key']}"
            service.start_trace(trace_id)
            analysis = service.analyze_shadow_evidence(
                topic_key=str(candidate["topic_key"]),
                candidate_rank=int(candidate["rank"]),
                diagnostic_title=str(candidate["diagnostic_representative_title"]),
                pre_audit=dict(candidate["evidence_pre_audit"]),
                evidence=evidence,
                evidence_metadata=evidence_metadata,
            )
            if analysis is None:
                rows.append(
                    {
                        **row,
                        "shadow_audit_status": "evidence_analysis_unavailable",
                        "trace": service.trace_summary(),
                    }
                )
                session.commit()
                continue
            dossier = cast(ShadowEvidenceDossier, analysis.value)
            taxonomy = service.taxonomize_shadow_trend(
                topic_key=str(candidate["topic_key"]),
                dossier=dossier,
                evidence=evidence,
                evidence_metadata=evidence_metadata,
                parent_run_id=analysis.run_id,
            )
            if taxonomy is None:
                rows.append(
                    {
                        **row,
                        "shadow_audit_status": "taxonomy_unavailable",
                        "evidence_analysis": _result_payload(analysis),
                        "trace": service.trace_summary(),
                    }
                )
                session.commit()
                continue
            taxonomy_value = cast(ShadowTrendTaxonomy, taxonomy.value)
            audit = service.audit_shadow_trend(
                topic_key=str(candidate["topic_key"]),
                dossier=dossier,
                taxonomy=taxonomy_value,
                evidence=evidence,
                evidence_metadata=evidence_metadata,
                analysis_run_id=analysis.run_id,
                parent_run_id=taxonomy.run_id,
            )
            if audit is None:
                rows.append(
                    {
                        **row,
                        "shadow_audit_status": "skeptic_audit_unavailable",
                        "evidence_analysis": _result_payload(analysis),
                        "taxonomy": _result_payload(taxonomy),
                        "trace": service.trace_summary(),
                    }
                )
                session.commit()
                continue
            audit_value = cast(ShadowTrendAudit, audit.value)
            rows.append(
                {
                    **row,
                    "shadow_audit_status": audit_value.decision,
                    "evidence_analysis": _result_payload(analysis),
                    "taxonomy": _result_payload(taxonomy),
                    "skeptic_audit": _result_payload(audit),
                    "trace": service.trace_summary(),
                }
            )
            session.commit()

    decisions = {
        status: sum(row["shadow_audit_status"] == status for row in rows)
        for status in sorted({str(row["shadow_audit_status"]) for row in rows})
    }
    payload = {
        "artifact_version": "semantic-adoption-agent-audit-v1",
        "generated_at": datetime.now(tz=UTC).isoformat(),
        "source_queue_sha256": source_sha,
        "source_checkpoint": source["source_checkpoint"],
        "source_outcome_embargo": source["source_outcome_embargo"],
        "llm_policy_version": LLM_POLICY_VERSION,
        "product_boundary": "shadow_only_no_act_no_probability",
        "product_release_ready_count": 0,
        "processed_limit": max(0, args.limit),
        "decision_counts": decisions,
        "candidates": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"decision_counts": decisions, "output_sha256": _hash(args.output)}, indent=2))


if __name__ == "__main__":
    main()
