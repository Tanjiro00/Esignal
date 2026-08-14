from packages.query_expansion import (
    MAX_NEW_SUGGESTIONS_PER_RUN,
    MAX_PENDING_SUGGESTIONS,
    QueryCandidate,
    evaluate_query_candidate,
    normalize_query,
    query_precision,
    should_demote_query,
)


def test_candidate_requires_product_and_problem_anchors() -> None:
    accepted = evaluate_query_candidate(
        QueryCandidate(
            query="Claude Code private repository safety",
            source_type="new_product_entity",
            source_entity="Claude Code",
            source_topic_id="topic-1",
            source_evidence_ids=("topic:1",),
            rationale="Evidence-backed entity and problem.",
            product_anchors=("Claude Code",),
            problem_anchors=("private repository safety",),
        )
    )
    broad = evaluate_query_candidate(
        QueryCandidate(
            query="AI tools",
            source_type="related_term",
            source_entity="AI",
            source_topic_id=None,
            source_evidence_ids=(),
            rationale="Too broad.",
            product_anchors=("AI",),
            problem_anchors=("workflow reliability",),
        )
    )

    assert accepted.accepted is True
    assert accepted.reason_codes == ("anchored_candidate",)
    assert broad.accepted is False
    assert "missing_problem_anchor" in broad.reason_codes
    assert normalize_query(" Claude Code: Safety! ") == "claude code safety"


def test_precision_and_explosion_limits_are_explicit() -> None:
    assert query_precision(retained_results=17, total_results=100) == 17
    assert should_demote_query(precision=14.9, sample_size=20) is True
    assert should_demote_query(precision=10, sample_size=19) is False
    assert MAX_NEW_SUGGESTIONS_PER_RUN == 10
    assert MAX_PENDING_SUGGESTIONS == 50
