from datetime import UTC, datetime, timedelta

from packages.channel_profile import (
    ChannelVideoSample,
    extract_channel_profile_v2,
    sanitize_channel_text,
)


def test_profile_extraction_strips_urls_handles_and_sponsor_boilerplate() -> None:
    cleaned = sanitize_channel_text(
        "Practical AI systems.\n"
        "Sponsored by Acme — use code TEST. https://sponsor.example.com/deal\n"
        "Follow me on @creator_handle and visit creator.ai"
    )

    assert cleaned == "Practical AI systems."
    assert "http" not in cleaned
    assert "creator.ai" not in cleaned
    assert "@creator_handle" not in cleaned
    assert "sponsored" not in cleaned.lower()


def test_profile_v2_separates_current_legacy_and_content_formats() -> None:
    now = datetime(2026, 7, 28, 12, tzinfo=UTC)
    samples = [
        ChannelVideoSample(
            id="current-1",
            title="I Tested Claude Code in Production",
            description="Hands-on developer workflow.",
            published_at=now - timedelta(days=5),
            duration_seconds=1_200,
            is_short=False,
            is_live=False,
            outlier_ratio=2.1,
        ),
        ChannelVideoSample(
            id="current-2",
            title="Claude Code Benchmark for Advanced Developers",
            description="A measured coding agent test.",
            published_at=now - timedelta(days=18),
            duration_seconds=1_500,
            is_short=False,
            is_live=False,
            outlier_ratio=1.8,
        ),
        ChannelVideoSample(
            id="current-short",
            title="Claude Code Tip",
            description="",
            published_at=now - timedelta(days=2),
            duration_seconds=45,
            is_short=True,
            is_live=False,
            outlier_ratio=0.8,
        ),
        ChannelVideoSample(
            id="legacy",
            title="Crypto Mining Rig Tutorial",
            description="Old mining workflow.",
            published_at=now - timedelta(days=500),
            duration_seconds=900,
            is_short=False,
            is_live=False,
            outlier_ratio=1.0,
        ),
    ]

    result = extract_channel_profile_v2(
        channel_title="Builder Lab",
        channel_description="Advanced AI engineering at https://builder.example.com",
        samples=samples,
        captured_at=now,
    )

    assert any("claude" in topic for topic in result.core_topics)
    assert all("example" not in topic for topic in result.core_topics)
    assert any("crypto" in topic or "mining" in topic for topic in result.legacy_topics)
    assert "Hands-on test" in result.successful_formats
    assert "Shorts" in result.preferred_formats
    assert result.audience_sophistication == "advanced"
    assert result.upload_cadence["sample_size"] == 3


def test_profile_topics_exclude_common_title_noise() -> None:
    now = datetime(2026, 7, 30, 12, tzinfo=UTC)
    samples = [
        ChannelVideoSample(
            id=f"video-{index}",
            title=title,
            description="Weekly technology news and analysis.",
            published_at=now - timedelta(days=index * 7),
            duration_seconds=900,
            is_short=False,
            is_live=False,
        )
        for index, title in enumerate(
            (
                "The junior developer job market is changing",
                "Why remote developer hiring is slowing",
                "How software engineering interviews changed",
            )
        )
    ]

    result = extract_channel_profile_v2(
        channel_title="Developer News",
        channel_description="Software careers and engineering hiring.",
        samples=samples,
        captured_at=now,
    )

    noisy = {"the", "and", "how", "why", "news"}
    assert noisy.isdisjoint(result.core_topics)
    assert any(
        "developer" in topic or "engineering" in topic or "hiring" in topic
        for topic in result.core_topics
    )


def test_profile_topics_reject_tracking_and_url_noise() -> None:
    now = datetime(2026, 7, 30, 12, tzinfo=UTC)
    result = extract_channel_profile_v2(
        channel_title="Software Careers",
        channel_description="SaaS and React careers. https://example.technology/path",
        samples=[
            ChannelVideoSample(
                id="video-1",
                title="Что с работой в IT?",
                description=(
                    "youtube shorts erid ghqabza1zi8 vfnxwvjksq cdn cookies unionconf React SaaS"
                ),
                published_at=now - timedelta(days=1),
                duration_seconds=900,
                is_short=False,
                is_live=False,
            )
        ],
        captured_at=now,
    )

    topics = " ".join((*result.core_topics, *result.adjacent_topics)).lower()
    assert "react" in topics or "saas" in topics
    for noise in (
        "youtube",
        "shorts",
        "erid",
        "ghqabza1zi8",
        "vfnxwvjksq",
        "cdn",
        "cookies",
        "unionconf",
    ):
        assert noise not in topics
