import json
from pathlib import Path

from packages.clustering import (
    MicrotopicDocument,
    cluster_microtopics_v5,
    compare_microtopic_identities,
    infer_microtopic_identity,
)

FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "evaluation"
    / "microtopic-v5-expert-cases.json"
)


def _cases() -> dict[str, list[MicrotopicDocument]]:
    payload = json.loads(FIXTURE_PATH.read_text())
    return {
        case["label"]: [
            MicrotopicDocument(
                id=document["id"],
                title=document["title"],
                description=document["description"],
                entities=tuple(document["entities"]),
            )
            for document in case["documents"]
        ]
        for case in payload["cases"]
    }


def test_expert_fixture_should_split() -> None:
    documents = _cases()["should_split"]
    decision = compare_microtopic_identities(
        infer_microtopic_identity(documents[0]),
        infer_microtopic_identity(documents[1]),
        semantic_overlap=0.81,
        publication_gap_days=2,
    )

    assert decision.action == "split"
    assert {
        "different_user_problem",
        "different_target_audience",
        "incompatible_core_claim",
    }.issubset(decision.reason_codes)


def test_expert_fixture_should_merge() -> None:
    documents = _cases()["should_merge"]
    decision = compare_microtopic_identities(
        infer_microtopic_identity(documents[0]),
        infer_microtopic_identity(documents[1]),
        semantic_overlap=0.84,
        publication_gap_days=4,
    )

    assert decision.action == "merge"
    assert decision.reason_codes == (
        "same_identity",
        "strong_semantic_overlap",
        "shared_temporal_window",
    )


def test_expert_fixture_should_reject() -> None:
    cluster = cluster_microtopics_v5(_cases()["should_reject"])[0]

    assert cluster.visible is False
    assert "missing_product_anchor" in cluster.reason_codes


def test_expert_fixture_valid_microtopic() -> None:
    clusters = cluster_microtopics_v5(_cases()["valid_microtopic"])
    visible = [cluster for cluster in clusters if cluster.visible]

    assert len(visible) == 1
    topic = visible[0]
    assert topic.label == "No-code AI agents for recurring business tasks"
    assert topic.specificity_score >= 70
    assert topic.thesis_support_ratio >= 0.8
    assert topic.audience == "business teams"
    assert topic.user_problem == "automate recurring business work"
    assert topic.core_claim == "adopt the workflow without coding"
    assert topic.workflow_context == "recurring business operations"
    assert topic.format_distribution


def test_specific_title_domain_wins_over_generic_agent_entity() -> None:
    identity = infer_microtopic_identity(
        MicrotopicDocument(
            id="developer-market",
            title="Developer tools reshape junior engineering hiring",
            description="AI agents are one part of a broader developer tooling shift.",
            entities=("AI agents", "Developer tools"),
        )
    )

    assert identity is not None
    assert identity.domain == "Developer tools"
    assert identity.facet == "subject"
