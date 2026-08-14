from packages.content_gap import build_content_gap_map, extract_content_pattern


def _pattern(
    video_id: str,
    title: str,
    *,
    content_format: str | None = None,
    outlier_ratio: float = 1.0,
):
    return extract_content_pattern(
        video_id=video_id,
        title=title,
        description="Stored evidence description.",
        entities=("Claude Code", "Coding agents"),
        transcript_format=content_format,
        channel_id=f"channel-{video_id}",
        outlier_ratio=outlier_ratio,
    )


def test_content_map_identifies_occupied_patterns_and_open_gap() -> None:
    patterns = [
        _pattern("video-1", "Claude Code Release Explained"),
        _pattern("video-2", "New Claude Code Release Is Here"),
        _pattern("video-3", "Claude Code Announcement Breakdown"),
    ]
    result = build_content_gap_map(
        topic_label="Claude Code for end-to-end software delivery",
        patterns=patterns,
        profile_audience="Developers building practical AI workflows.",
        preferred_formats=["Hands-on test"],
        demand_question="Can it safely handle a private repository?",
        evidence_refs=["video:video-1", "video:video-2", "comment:comment-1"],
        channel_fit=82,
        production_feasibility=88,
        timing=76,
        brand_risk=0,
    )

    assert result["occupied_pattern"]["format"]["value"] == "release explainer"
    opportunities = result["opportunities"]
    assert len(opportunities) == 3
    assert opportunities[0]["rank"] == 1
    assert opportunities[0]["open_gap"]["is_open"] is True
    assert opportunities[0]["evidence"]
    assert opportunities[0]["title"] == "Claude Code for end-to-end software delivery"
    assert "video format" in opportunities[0]["differentiation"]
    assert "I tested" not in " ".join(opportunities[0]["title_directions"])
    assert opportunities[0]["why_primary"]


def test_primary_opportunity_differs_from_majority_evidence_cell() -> None:
    patterns = [
        _pattern("video-1", "How to Use Claude Code: Tutorial"),
        _pattern("video-2", "Claude Code Complete Tutorial"),
        _pattern("video-3", "A Beginner Guide to Claude Code"),
        _pattern("video-4", "Claude Code Tutorial for Developers"),
    ]
    result = build_content_gap_map(
        topic_label="Claude Code with controlled repository access",
        patterns=patterns,
        profile_audience="Developers.",
        preferred_formats=["Hands-on test"],
        demand_question="What permissions are safe?",
        evidence_refs=[f"video:{pattern.video_id}" for pattern in patterns],
        channel_fit=78,
        production_feasibility=80,
        timing=85,
        brand_risk=0,
    )

    primary = result["opportunities"][0]
    assert primary["open_gap"]["format"] != "tutorial"
    assert primary["open_gap"]["proof_type"] != "demonstration"
    assert set(primary["evidence"]) == {
        "video:video-1",
        "video:video-2",
        "video:video-3",
        "video:video-4",
    }


def test_content_gap_does_not_expose_channel_mission_as_audience() -> None:
    patterns = [
        _pattern("video-1", "Claude Code Tutorial for Developers"),
        _pattern("video-2", "Claude Code Guide for Developers"),
    ]

    result = build_content_gap_map(
        topic_label="Claude Code agent workflows",
        patterns=patterns,
        profile_audience=(
            "Sifting through all the AI noise to share what actually matters "
            "- New videos every week"
        ),
        preferred_formats=["Hands-on test"],
        demand_question="Which workflow is reliable?",
        evidence_refs=["video:video-1", "video:video-2"],
        channel_fit=68,
        production_feasibility=75,
        timing=70,
        brand_risk=0,
    )

    opportunities = result["opportunities"]
    assert all(opportunity["open_gap"]["audience"] == "developers" for opportunity in opportunities)
    assert all("Sifting through" not in str(opportunity["title"]) for opportunity in opportunities)


def test_generic_fallback_question_does_not_inflate_demand_or_novelty() -> None:
    patterns = [
        _pattern("video-1", "Claude Code Release Explained"),
        _pattern("video-2", "Claude Code Release Explained Again"),
        _pattern("video-3", "Claude Code Announcement"),
    ]

    result = build_content_gap_map(
        topic_label="Claude Code repository workflows",
        patterns=patterns,
        profile_audience="Developers.",
        preferred_formats=["Evidence-led explainer"],
        demand_question=(
            "What is observably changing, who is affected, and what remains uncertain?"
        ),
        evidence_refs=[f"video:{pattern.video_id}" for pattern in patterns],
        channel_fit=78,
        production_feasibility=80,
        timing=85,
        brand_risk=0,
        demand_supported=False,
    )

    assert all(
        opportunity["score_components"]["unmet_demand_strength"] == 0
        for opportunity in result["opportunities"]
    )
    assert all(
        opportunity["score_components"]["novelty"] <= 44 for opportunity in result["opportunities"]
    )
    assert all(opportunity["release_ready"] is False for opportunity in result["opportunities"])


def test_confirmed_cross_video_demand_releases_one_evidence_backed_insight() -> None:
    patterns = [
        _pattern("video-1", "Claude Code Release Explained"),
        _pattern("video-2", "Claude Code Release Explained Again"),
        _pattern("video-3", "Claude Code Announcement"),
    ]
    demand_question = "Which repository permissions are safe for a production team?"

    result = build_content_gap_map(
        topic_label="Claude Code repository workflows",
        patterns=patterns,
        profile_audience="Developers.",
        preferred_formats=["Evidence-led explainer"],
        demand_question=demand_question,
        evidence_refs=[
            "video:video-1",
            "video:video-2",
            "comment:comment-1",
        ],
        channel_fit=78,
        production_feasibility=80,
        timing=85,
        brand_risk=0,
        demand_supported=True,
    )

    primary = result["opportunities"][0]
    assert primary["release_ready"] is True
    assert primary["insight_status"] == "evidence_backed"
    assert primary["insight_type"] == "audience_demand"
    assert primary["insight_statement"] == demand_question
    assert primary["insight_evidence"] == ["comment:comment-1"]


def test_repeated_performance_split_requires_semantic_evidence_audit() -> None:
    patterns = [
        _pattern(
            "video-1",
            "Claude Code Release Explained",
            outlier_ratio=0.8,
        ),
        _pattern(
            "video-2",
            "Claude Code Release Notes",
            outlier_ratio=0.9,
        ),
        _pattern(
            "video-3",
            "Claude Code Announcement",
            outlier_ratio=1.0,
        ),
        _pattern(
            "video-4",
            "Run Claude Code Locally on Your PC",
            outlier_ratio=2.0,
        ),
        _pattern(
            "video-5",
            "Local Claude Code Workflow on Owned Hardware",
            outlier_ratio=2.4,
        ),
        _pattern(
            "video-6",
            "Self-Hosted Claude Code on Your PC",
            outlier_ratio=2.1,
        ),
    ]

    result = build_content_gap_map(
        topic_label="Claude Code repository workflows",
        patterns=patterns,
        profile_audience="Developers.",
        preferred_formats=["Evidence-led explainer"],
        demand_question="",
        evidence_refs=[f"video:{pattern.video_id}" for pattern in patterns],
        channel_fit=78,
        production_feasibility=80,
        timing=85,
        brand_risk=0,
    )

    primary = result["opportunities"][0]
    assert primary["release_ready"] is False
    assert primary["insight_type"] == "performance_pattern_candidate"
    assert "has not passed semantic evidence audit" in primary["insight_statement"]
    assert primary["insight_metrics"]["performance_pattern"]["group_size"] == 3
    assert primary["insight_metrics"]["performance_pattern"]["dimension"] in {
        "claim",
        "context",
    }


def test_format_emotion_and_proof_type_cannot_release_an_insight() -> None:
    patterns = [
        _pattern(
            "video-1",
            "Claude Code Release Explained",
            content_format="release explainer",
            outlier_ratio=0.8,
        ),
        _pattern(
            "video-2",
            "Claude Code Release Notes",
            content_format="release explainer",
            outlier_ratio=0.9,
        ),
        _pattern(
            "video-3",
            "Claude Code Announcement",
            content_format="release explainer",
            outlier_ratio=1.0,
        ),
        _pattern(
            "video-4",
            "Claude Code Production Case Study",
            content_format="case study",
            outlier_ratio=2.0,
        ),
        _pattern(
            "video-5",
            "Claude Code Real Project Case Study",
            content_format="case study",
            outlier_ratio=2.4,
        ),
        _pattern(
            "video-6",
            "Claude Code Team Case Study",
            content_format="case study",
            outlier_ratio=2.1,
        ),
    ]

    result = build_content_gap_map(
        topic_label="Claude Code repository workflows",
        patterns=patterns,
        profile_audience="Developers.",
        preferred_formats=["Evidence-led explainer"],
        demand_question="",
        evidence_refs=[f"video:{pattern.video_id}" for pattern in patterns],
        channel_fit=78,
        production_feasibility=80,
        timing=85,
        brand_risk=0,
    )

    assert all(opportunity["release_ready"] is False for opportunity in result["opportunities"])
