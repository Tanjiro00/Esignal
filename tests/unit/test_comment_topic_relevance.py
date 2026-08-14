import json
from pathlib import Path

from packages.demand import (
    RELEVANCE_MODEL_VERSION,
    CommentTopicRelevanceInput,
    classify_comment_topic_relevance,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_comment_topic_relevance_regression_fixture() -> None:
    fixture = json.loads(
        (REPO_ROOT / "fixtures" / "evaluation" / "comment-topic-relevance-v1.json").read_text()
    )

    assert fixture["model_version"] == RELEVANCE_MODEL_VERSION
    for case in fixture["cases"]:
        result = classify_comment_topic_relevance(
            CommentTopicRelevanceInput(
                comment_text=case["comment"],
                intent=case["intent"],
                demand_probability=case["demand_probability"],
                spam_probability=0.02,
                topic_label=case["topic_label"],
                topic_entities=tuple(case["topic_entities"]),
                video_title=case["video_title"],
                video_description="",
                video_entities=tuple(case["video_entities"]),
            )
        )
        assert result.is_relevant is case["expected_relevant"], case["id"]
        assert result.model_version == RELEVANCE_MODEL_VERSION
        assert 0 <= result.relevance_score <= 1
        assert result.reason_codes


def test_duplicate_echo_probability_penalizes_but_does_not_double_count() -> None:
    base = CommentTopicRelevanceInput(
        comment_text="Is this free?",
        intent="pricing_request",
        demand_probability=0.9,
        spam_probability=0.02,
        topic_label="Free, local and unlimited AI video generation",
        topic_entities=("AI video generation",),
        video_title="Generate unlimited AI videos on your PC",
        video_description="",
        video_entities=("AI video generation",),
    )
    unique = classify_comment_topic_relevance(base)
    echoed = classify_comment_topic_relevance(
        CommentTopicRelevanceInput(
            **{
                **base.__dict__,
                "duplicate_count": 4,
            }
        )
    )

    assert unique.duplicate_or_echo_probability == 0
    assert echoed.duplicate_or_echo_probability > 0
    assert echoed.relevance_score < unique.relevance_score
