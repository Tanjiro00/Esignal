from datetime import UTC, datetime, timedelta

from packages.backtest.youniverse import StructuralVideo
from packages.backtest.youniverse_replay import (
    StructuralCandidateIndex,
    StructuralOutcomeEvaluator,
    StructuralReplayPolicy,
)
from packages.clustering import (
    MicrotopicDocument,
    cluster_microtopics_v8,
    infer_microtopic_identity_v8,
    topic_key_v8,
)


def _document(identifier: str, title: str) -> MicrotopicDocument:
    return MicrotopicDocument(id=identifier, title=title, description="", entities=())


def _video(identifier: str, channel: str, title: str, days: int) -> StructuralVideo:
    return StructuralVideo(
        video_id=identifier,
        channel_id=channel,
        title=title,
        description="",
        tags=(),
        category="Science & Technology",
        upload_date=datetime(2026, 4, 1, tzinfo=UTC) + timedelta(days=days),
    )


def test_v8_rejects_product_wide_creator_activity() -> None:
    assert infer_microtopic_identity_v8(_document("generic", "Claude Code is insane")) is None


def test_v8_keeps_claim_object_but_removes_presentation_format() -> None:
    clusters = cluster_microtopics_v8(
        [
            _document("tutorial", "Claude Code memory tutorial for beginners"),
            _document("explainer", "Claude Code persistent context explained"),
        ]
    )

    assert len(clusters) == 1
    assert clusters[0].label == "Claude Code — memory and persistent context"
    assert clusters[0].document_ids == ("tutorial", "explainer")


def test_v8_separates_different_claims_for_same_product() -> None:
    identities = [
        infer_microtopic_identity_v8(_document("memory", "Claude Code memory explained")),
        infer_microtopic_identity_v8(
            _document("tokens", "Claude Code is eating your tokens — here is the fix")
        ),
    ]

    assert all(identity is not None for identity in identities)
    assert len({topic_key_v8(identity) for identity in identities if identity}) == 2


def test_v8_normalizes_material_product_version() -> None:
    clusters = cluster_microtopics_v8(
        [
            _document("one", "DeepSeek V4 release cuts inference price"),
            _document("two", "DeepSeek v4.0 pricing is cheaper"),
        ]
    )

    assert len(clusters) == 1
    assert clusters[0].primary_entity == "DeepSeek V4"
    assert clusters[0].facet == "price_cost"


def test_v8_comparison_key_does_not_depend_on_title_order() -> None:
    clusters = cluster_microtopics_v8(
        [
            _document("one", "Claude Code vs OpenAI Codex for real coding work"),
            _document("two", "OpenAI Codex versus Claude Code benchmark"),
        ]
    )

    assert len(clusters) == 1
    assert clusters[0].facet == "product_comparison"
    assert clusters[0].primary_entity == "Claude Code / OpenAI Codex"


def test_v8_supports_concrete_domain_topic_without_named_product() -> None:
    identity = infer_microtopic_identity_v8(
        _document("character", "Consistent AI characters across every video scene")
    )

    assert identity is not None
    assert identity.primary_entity == "AI video generation"
    assert identity.facet == "consistent_characters"


def test_v8_rejects_domain_concept_tautology() -> None:
    assert (
        infer_microtopic_identity_v8(
            _document("broad", "The best AI video generators available now")
        )
        is None
    )


def test_v8_candidate_and_outcome_use_same_identity() -> None:
    videos = [
        _video("prior-a", "a", "Claude Code memory tutorial", -5),
        _video("prior-b", "b", "Claude Code persistent context explained", -3),
        _video("future-c", "c", "Claude Code memory setup", 5),
        _video("future-d", "d", "Claude Code persistent context guide", 7),
        _video("future-e", "e", "Claude Code memory workflow", 9),
        _video("future-f", "f", "Claude Code memory review", 11),
    ]
    policy = StructuralReplayPolicy(adoption_supply_growth_threshold=1.0)
    index = StructuralCandidateIndex(videos, policy=policy, taxonomy="v8")
    evaluator = StructuralOutcomeEvaluator(videos, (), (), policy=policy, taxonomy="v8")

    state = next(iter(index.states_at(datetime(2026, 4, 1, tzinfo=UTC)).values()))
    outcome = evaluator.evaluate(state)

    assert state.label == "Claude Code — memory and persistent context"
    assert outcome.adoption_fired is True
    assert outcome.future_video_count == 4
