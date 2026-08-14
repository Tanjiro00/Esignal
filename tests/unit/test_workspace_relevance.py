from packages.channel_fit import (
    DiscoveryOccurrenceEvidence,
    assess_workspace_relevance,
)


def test_workspace_relevance_rejects_accidental_cross_topic_video() -> None:
    result = assess_workspace_relevance(
        topic_values=["Metric-Driven AI Agent Loops for Business Work"],
        core_topic_values=[
            "software engineering careers",
            "developer hiring and interviews",
            "IT labor market",
        ],
        evidence_video_ids=[f"video-{index}" for index in range(6)],
        plan_query_count=16,
        occurrences=[
            DiscoveryOccurrenceEvidence(
                video_id="video-5",
                query_id="query-qa",
                query="QA automation career transition 2026",
            )
        ],
    )

    assert result["eligible"] is False
    assert result["matching_video_count"] == 0
    assert "core_topic_mismatch" in result["reason_codes"]


def test_workspace_relevance_requires_repeated_personal_evidence() -> None:
    result = assess_workspace_relevance(
        topic_values=["Junior developer interview preparation in the 2026 job market"],
        core_topic_values=[
            "software engineering careers",
            "developer hiring and interviews",
            "IT labor market",
        ],
        evidence_video_ids=["video-1", "video-2", "video-3"],
        plan_query_count=16,
        occurrences=[
            DiscoveryOccurrenceEvidence(
                video_id="video-1",
                query_id="query-junior",
                query="junior developer job market 2026",
            ),
            DiscoveryOccurrenceEvidence(
                video_id="video-2",
                query_id="query-interview",
                query="JavaScript frontend system design interview",
            ),
        ],
    )

    assert result["eligible"] is True
    assert result["matching_video_count"] == 2
    assert result["personal_evidence_coverage"] == 0.667


def test_personal_query_evidence_recovers_from_stale_profile_topics() -> None:
    result = assess_workspace_relevance(
        topic_values=["junior developer job market 2026"],
        core_topic_values=["shorts", "youtube", "erid"],
        evidence_video_ids=["video-1", "video-2", "video-3"],
        plan_query_count=16,
        occurrences=[
            DiscoveryOccurrenceEvidence(
                video_id="video-1",
                query_id="query-junior",
                query="junior developer job market 2026",
            ),
            DiscoveryOccurrenceEvidence(
                video_id="video-2",
                query_id="query-junior",
                query="junior developer job market 2026",
            ),
            DiscoveryOccurrenceEvidence(
                video_id="video-3",
                query_id="query-junior",
                query="junior developer job market 2026",
            ),
        ],
    )

    assert result["eligible"] is True
    assert result["core_topic_overlap"] == 0
    assert result["reason_codes"] == ["personal_query_evidence_confirmed"]
    assert result["version"] == "workspace-relevance-v2"


def test_workspace_without_personal_plan_keeps_legacy_behavior() -> None:
    result = assess_workspace_relevance(
        topic_values=["Any topic"],
        core_topic_values=[],
        evidence_video_ids=["video-1"],
        plan_query_count=0,
        occurrences=[],
    )

    assert result["eligible"] is True
    assert result["reason_codes"] == ["no_personal_discovery_plan"]
