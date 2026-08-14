from dataclasses import dataclass
from datetime import UTC, datetime

from packages.clustering.evidence_quality import (
    assess_evidence_quality,
    assess_evidence_release,
    collapse_near_duplicate_evidence,
    titles_are_near_duplicates,
)


@dataclass(frozen=True)
class _Evidence:
    video_id: str
    channel_id: str
    title: str
    upload_date: datetime = datetime(2026, 1, 1, tzinfo=UTC)


def test_copy_family_ignores_punctuation_and_clickable_format_noise() -> None:
    assert titles_are_near_duplicates(
        "Higgsfield AI is DEAD | Use This FREE HeyGen Trick Instead",
        "Higgsfield AI is DEAD 😱 — Use This FREE HeyGen Trick Instead",
    )


def test_copy_family_credits_only_one_channel_evidence_item() -> None:
    rows = (
        _Evidence(
            "b",
            "copy-channel",
            "Claude Code memory tutorial",
            datetime(2026, 1, 2, tzinfo=UTC),
        ),
        _Evidence(
            "a",
            "original-channel",
            "Claude Code memory tutorial!",
            datetime(2026, 1, 1, tzinfo=UTC),
        ),
    )

    collapsed = collapse_near_duplicate_evidence(rows)

    assert collapsed == (rows[1],)


def test_quality_gate_accepts_paraphrased_concrete_identity() -> None:
    assessment = assess_evidence_quality(
        (
            _Evidence("a", "channel-a", "Claude Code memory tutorial"),
            _Evidence("b", "channel-b", "Persistent context in Claude Code explained"),
        )
    )

    assert assessment.accepted is True
    assert assessment.title_family_count == 2
    assert assessment.dominant_identity_label == "Claude Code — memory and persistent context"


def test_quality_gate_rejects_semantically_broad_cluster() -> None:
    assessment = assess_evidence_quality(
        (
            _Evidence("a", "channel-a", "Claude Code memory tutorial"),
            _Evidence("b", "channel-b", "ChatGPT AI image generation workflow"),
        )
    )

    assert assessment.accepted is False
    assert "insufficient_concrete_identity_evidence" in assessment.reason_codes


def test_release_pre_audit_accepts_new_concept_without_dictionary_entry() -> None:
    assessment = assess_evidence_release(
        (
            _Evidence("a", "channel-a", "Translate video into any language with AI dubbing"),
            _Evidence("b", "channel-b", "Voice translation and dubbing for creator videos"),
        )
    )

    assert assessment.pre_audit_passed is True
    assert "translation" in assessment.shared_anchor_concepts
    assert "dubbing" in assessment.shared_anchor_concepts


def test_release_pre_audit_rejects_generic_generator_roundup() -> None:
    assessment = assess_evidence_release(
        (
            _Evidence("a", "channel-a", "5 free unlimited AI video generators"),
            _Evidence("b", "channel-b", "Best AI video generators available now"),
        )
    )

    assert assessment.pre_audit_passed is False
    assert "no_shared_concrete_anchor" in assessment.reason_codes


def test_release_pre_audit_rejects_clickbait_as_shared_anchor() -> None:
    assessment = assess_evidence_release(
        (
            _Evidence("a", "channel-a", "This Chinese AI model changes everything"),
            _Evidence("b", "channel-b", "New Chinese AI agent is insane"),
        )
    )

    assert assessment.pre_audit_passed is False
    assert assessment.shared_anchor_concepts == ()


def test_release_pre_audit_keeps_local_inference_as_a_concept() -> None:
    assessment = assess_evidence_release(
        (
            _Evidence("a", "channel-a", "Run an AI video model locally"),
            _Evidence("b", "channel-b", "Local AI video inference on a GPU"),
        )
    )

    assert assessment.pre_audit_passed is True
    assert "local" in assessment.shared_anchor_concepts


def test_release_pre_audit_rejects_non_english_majority() -> None:
    assessment = assess_evidence_release(
        (
            _Evidence("a", "channel-a", "Google Flow aur Gemini ko free me kaise use kare"),
            _Evidence("b", "channel-b", "Google AI से free video banaye"),
            _Evidence("c", "channel-c", "Gemini Flow free access in Hindi"),
        )
    )

    assert assessment.pre_audit_passed is False
    assert "non_english_evidence_majority" in assessment.reason_codes


def test_release_pre_audit_collapses_paraphrased_copy_family() -> None:
    assessment = assess_evidence_release(
        (
            _Evidence("a", "channel-a", "China shocked the AI world with a 10 trillion model"),
            _Evidence("b", "channel-b", "China shocked everyone with a 10 trillion AI model"),
        )
    )

    assert assessment.pre_audit_passed is False
    assert assessment.title_family_count == 1
