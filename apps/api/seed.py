from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from hashlib import sha256
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from apps.api.config import get_settings
from apps.api.database import SessionLocal
from apps.api.demo import (
    DEMO_OWNED_CHANNEL_ID,
    DEMO_REFERENCE_AT,
    DEMO_USER_ID,
    DEMO_WORKSPACE_ID,
    demo_id,
)
from apps.api.lifecycle import BACKFILL_VERSION, HISTORY_VERSION
from apps.api.models import (
    ChannelBaseline,
    ChannelProfile,
    CommentFeature,
    CommentFetchRun,
    CommentTopicRelevance,
    CommentTopicRelevanceEvent,
    ContentBrief,
    DemandCluster,
    DemandClusterComment,
    DigestRun,
    DigestSubscription,
    DiscoveryQueryRecord,
    EvaluationLabel,
    FieldProvenance,
    OutcomeSuggestion,
    ProductEvent,
    ProviderFetch,
    ProviderHealth,
    PublishedOutcome,
    QuerySuggestion,
    RawPayloadLink,
    Signal,
    SignalAction,
    SignalPackaging,
    SignalReview,
    SignalReviewEvent,
    Topic,
    TopicContentGap,
    TopicContentPattern,
    TopicLifecycleSummary,
    TopicLifecycleTransition,
    TopicSnapshot,
    TopicSnapshotBucket,
    TopicVideoMembership,
    TranscriptFetchRun,
    TranscriptSegment,
    User,
    VideoEmbedding,
    VideoFeature,
    VideoSnapshot,
    VideoSnapshotJob,
    VideoTranscript,
    Workspace,
    WorkspaceChannel,
    WorkspaceMember,
    WorkspaceOnboarding,
    WorkspaceSignalScore,
    YoutubeChannel,
    YoutubeComment,
    YoutubeOAuthAuditEvent,
    YoutubeOAuthConnection,
    YoutubeOAuthState,
    YoutubeOwnedAnalytics,
    YoutubeVideo,
)
from apps.api.product_analytics import record_product_event
from apps.api.reviews import ensure_signal_review
from apps.worker.digests import DigestService
from packages.demand import RELEVANCE_MODEL_VERSION
from packages.production_feasibility import assess_production_feasibility
from packages.scoring import ScoreComponents, calculate_early_signal_score

DEMO_NOW = DEMO_REFERENCE_AT
REPO_ROOT = Path(__file__).resolve().parents[2]

TOPICS: tuple[dict[str, Any], ...] = (
    {
        "label": "Claude Code autonomous workflows",
        "aliases": ["Claude Code agents", "autonomous coding workflows"],
        "entities": ["Claude Code", "AI agents", "developer tools"],
        "stage": "Emerging",
        "confidence": "High",
        "first_seen_days": 10,
        "window": (4, 8),
        "thesis": (
            "Claude Code is moving from an experimental CLI to a reliable way to automate "
            "real development tasks end-to-end with minimal human input."
        ),
        "why": [
            "Real workflow demos are accelerating across independent builder channels.",
            "Coverage is spreading from developer specialists into productivity creators.",
            "Viewer questions focus on safety and deployment, not basic awareness.",
        ],
        "components": ScoreComponents(96, 92, 97, 93, 90, 88, 86, 20, 16),
        "fit": 92.0,
        "demand": (
            "Private-repository safety",
            "How do I safely let Claude Code run end-to-end on my private repos?",
        ),
        "category": "AI coding",
    },
    {
        "label": "AI browser agents buying products",
        "aliases": ["shopping agents", "transactional browser agents"],
        "entities": ["browser agents", "shopping", "automation"],
        "stage": "Breakout",
        "confidence": "High",
        "first_seen_days": 18,
        "window": (3, 6),
        "thesis": (
            "Browser agents are crossing from navigation demos into real purchase decisions, "
            "creating urgent questions about trust, permission, and refunds."
        ),
        "why": [
            "Upload velocity doubled in the last 72 hours.",
            "Independent consumer-tech and AI channels are entering together.",
            "Large general-tech channels are present but do not yet dominate results.",
        ],
        "components": ScoreComponents(94, 88, 90, 91, 82, 90, 92, 42, 22),
        "fit": 87.0,
        "demand": (
            "Trust and transaction control",
            "How do I stop an agent from spending money or choosing the wrong product?",
        ),
        "category": "AI agents",
    },
    {
        "label": "Local video generation on consumer GPUs",
        "aliases": ["local AI video", "consumer GPU video models"],
        "entities": ["AI video", "GPUs", "local models"],
        "stage": "Seed",
        "confidence": "Medium",
        "first_seen_days": 7,
        "window": (7, 14),
        "thesis": (
            "New compressed video models are making useful local generation plausible on "
            "consumer graphics cards, but setup evidence is still fragmented."
        ),
        "why": [
            "Small technical channels are publishing reproducible benchmarks.",
            "Search appearances are rising from a low base.",
            "Demand concentrates on hardware-specific settings and quality tradeoffs.",
        ],
        "components": ScoreComponents(70, 72, 84, 80, 92, 64, 68, 15, 36),
        "fit": 78.0,
        "demand": (
            "Hardware-specific benchmarks",
            "What settings actually work for consistent 1080p video on a 16 GB GPU?",
        ),
        "category": "AI video",
    },
    {
        "label": "AI wearables replacing the phone",
        "aliases": ["AI pins", "screenless AI devices"],
        "entities": ["AI wearables", "consumer devices"],
        "stage": "Mass Market",
        "confidence": "Medium",
        "first_seen_days": 55,
        "window": (1, 3),
        "thesis": (
            "Always-on AI wearables are attracting broad coverage, but generic replacement-"
            "for-phone angles are already crowded."
        ),
        "why": [
            "Large consumer-tech channels now contribute most new views.",
            "Upload acceleration has flattened after launch coverage.",
            "Differentiated accessibility and privacy angles still have room.",
        ],
        "components": ScoreComponents(62, 90, 72, 68, 55, 84, 58, 78, 34),
        "fit": 51.0,
        "demand": (
            "Differentiation from smartwatches",
            "What can this do that a phone and smartwatch cannot already do?",
        ),
        "category": "Consumer AI",
    },
    {
        "label": "Open-weight reasoning model benchmarks",
        "aliases": ["open reasoning models", "reasoning benchmark videos"],
        "entities": ["open-weight models", "benchmarks"],
        "stage": "Saturated",
        "confidence": "High",
        "first_seen_days": 80,
        "window": (0, 2),
        "thesis": (
            "Benchmark comparisons remain popular, but repeated leaderboard summaries offer "
            "little novelty and now require a distinct real-world test to win."
        ),
        "why": [
            "Search results are dominated by established AI channels.",
            "Title and angle diversity has collapsed around identical benchmarks.",
            "New uploads underperform channel baselines unless they add original tests.",
        ],
        "components": ScoreComponents(48, 94, 60, 64, 38, 82, 34, 92, 28),
        "fit": 66.0,
        "demand": (
            "Real-world proof",
            "Can someone test these models on a real project instead of another leaderboard?",
        ),
        "category": "Foundation models",
    },
)

CHANNEL_PREFIXES = (
    "Applied",
    "Practical",
    "Signal",
    "Build",
    "Future",
    "Independent",
    "Systems",
    "Everyday",
    "Open",
    "Deep",
)
CHANNEL_SUFFIXES = ("AI", "Engineering", "Tools", "Tech", "Automation")


def _clear_demo(session: Session) -> None:
    topic_ids = [demo_id("topic", index) for index in range(len(TOPICS))]
    demo_signal_ids = select(Signal.id).where(Signal.topic_id.in_(topic_ids))
    demo_video_ids = select(YoutubeVideo.id).where(YoutubeVideo.youtube_video_id.like("esdemo%"))
    demo_comment_ids = select(YoutubeComment.id).where(YoutubeComment.video_id.in_(demo_video_ids))
    demo_channel_ids = select(YoutubeChannel.id).where(
        YoutubeChannel.youtube_channel_id.like("UCESDEMO%")
    )
    mock_fetch_ids = select(ProviderFetch.id).where(ProviderFetch.provider.like("mock_%"))
    expansion_query_ids = [
        value
        for value in session.scalars(
            select(QuerySuggestion.discovery_query_id).where(
                QuerySuggestion.source_topic_id.in_(topic_ids),
                QuerySuggestion.discovery_query_id.is_not(None),
            )
        )
        if value is not None
    ]

    session.execute(delete(ProductEvent).where(ProductEvent.signal_id.in_(demo_signal_ids)))
    session.execute(delete(QuerySuggestion).where(QuerySuggestion.source_topic_id.in_(topic_ids)))
    if expansion_query_ids:
        session.execute(
            delete(DiscoveryQueryRecord).where(
                DiscoveryQueryRecord.id.in_(expansion_query_ids),
                DiscoveryQueryRecord.source == "query_expansion",
            )
        )
    session.execute(
        delete(YoutubeOAuthAuditEvent).where(
            YoutubeOAuthAuditEvent.workspace_id == DEMO_WORKSPACE_ID
        )
    )
    session.execute(
        delete(YoutubeOAuthState).where(YoutubeOAuthState.workspace_id == DEMO_WORKSPACE_ID)
    )
    session.execute(
        delete(YoutubeOwnedAnalytics).where(YoutubeOwnedAnalytics.workspace_id == DEMO_WORKSPACE_ID)
    )
    session.execute(
        delete(YoutubeOAuthConnection).where(
            YoutubeOAuthConnection.workspace_id == DEMO_WORKSPACE_ID
        )
    )
    session.execute(
        delete(OutcomeSuggestion).where(OutcomeSuggestion.signal_id.in_(demo_signal_ids))
    )
    session.execute(delete(PublishedOutcome).where(PublishedOutcome.signal_id.in_(demo_signal_ids)))
    session.execute(delete(SignalPackaging).where(SignalPackaging.signal_id.in_(demo_signal_ids)))
    session.execute(delete(ContentBrief).where(ContentBrief.signal_id.in_(demo_signal_ids)))
    session.execute(delete(SignalAction).where(SignalAction.signal_id.in_(demo_signal_ids)))
    session.execute(delete(EvaluationLabel).where(EvaluationLabel.topic_id.in_(topic_ids)))
    session.execute(
        delete(SignalReviewEvent).where(SignalReviewEvent.signal_id.in_(demo_signal_ids))
    )
    session.execute(delete(SignalReview).where(SignalReview.signal_id.in_(demo_signal_ids)))
    session.execute(
        delete(CommentTopicRelevanceEvent).where(CommentTopicRelevanceEvent.topic_id.in_(topic_ids))
    )
    session.execute(
        delete(CommentTopicRelevance).where(CommentTopicRelevance.topic_id.in_(topic_ids))
    )
    session.execute(
        delete(DemandClusterComment).where(
            DemandClusterComment.demand_cluster_id.in_(
                select(DemandCluster.id).where(DemandCluster.topic_id.in_(topic_ids))
            )
        )
    )
    session.execute(delete(DemandCluster).where(DemandCluster.topic_id.in_(topic_ids)))
    session.execute(
        delete(TranscriptSegment).where(
            TranscriptSegment.transcript_id.in_(
                select(VideoTranscript.id).where(VideoTranscript.video_id.in_(demo_video_ids))
            )
        )
    )
    session.execute(
        delete(TranscriptFetchRun).where(TranscriptFetchRun.video_id.in_(demo_video_ids))
    )
    session.execute(delete(VideoTranscript).where(VideoTranscript.video_id.in_(demo_video_ids)))
    session.execute(delete(CommentFeature).where(CommentFeature.comment_id.in_(demo_comment_ids)))
    session.execute(delete(YoutubeComment).where(YoutubeComment.video_id.in_(demo_video_ids)))
    session.execute(delete(CommentFetchRun).where(CommentFetchRun.video_id.in_(demo_video_ids)))
    session.execute(
        delete(WorkspaceSignalScore).where(WorkspaceSignalScore.signal_id.in_(demo_signal_ids))
    )
    session.execute(delete(Signal).where(Signal.topic_id.in_(topic_ids)))
    session.execute(
        delete(TopicLifecycleTransition).where(TopicLifecycleTransition.topic_id.in_(topic_ids))
    )
    session.execute(
        delete(TopicLifecycleSummary).where(TopicLifecycleSummary.topic_id.in_(topic_ids))
    )
    session.execute(delete(TopicSnapshot).where(TopicSnapshot.topic_id.in_(topic_ids)))
    session.execute(delete(TopicSnapshotBucket).where(TopicSnapshotBucket.topic_id.in_(topic_ids)))
    session.execute(delete(TopicContentGap).where(TopicContentGap.topic_id.in_(topic_ids)))
    session.execute(delete(TopicContentPattern).where(TopicContentPattern.topic_id.in_(topic_ids)))
    session.execute(
        delete(TopicVideoMembership).where(TopicVideoMembership.topic_id.in_(topic_ids))
    )
    session.execute(delete(VideoSnapshot).where(VideoSnapshot.video_id.in_(demo_video_ids)))
    session.execute(delete(VideoSnapshotJob).where(VideoSnapshotJob.video_id.in_(demo_video_ids)))
    session.execute(delete(VideoEmbedding).where(VideoEmbedding.video_id.in_(demo_video_ids)))
    session.execute(delete(VideoFeature).where(VideoFeature.video_id.in_(demo_video_ids)))
    session.execute(delete(ChannelBaseline).where(ChannelBaseline.channel_id.in_(demo_channel_ids)))
    session.execute(delete(ChannelProfile).where(ChannelProfile.channel_id.in_(demo_channel_ids)))
    session.execute(
        delete(WorkspaceChannel).where(WorkspaceChannel.channel_id.in_(demo_channel_ids))
    )
    session.execute(delete(YoutubeVideo).where(YoutubeVideo.id.in_(demo_video_ids)))
    session.execute(delete(Topic).where(Topic.id.in_(topic_ids)))
    session.execute(delete(YoutubeChannel).where(YoutubeChannel.id.in_(demo_channel_ids)))
    session.execute(
        delete(FieldProvenance).where(FieldProvenance.provider_fetch_id.in_(mock_fetch_ids))
    )
    session.execute(
        delete(RawPayloadLink).where(RawPayloadLink.provider_fetch_id.in_(mock_fetch_ids))
    )
    session.execute(delete(ProviderHealth).where(ProviderHealth.provider.like("mock_%")))
    session.execute(delete(ProviderFetch).where(ProviderFetch.id.in_(mock_fetch_ids)))
    session.commit()


def _payload(path: str) -> tuple[str, str]:
    absolute = REPO_ROOT / path
    content = absolute.read_bytes()
    return path, sha256(content).hexdigest()


def _seed_provider_operations(session: Session) -> dict[str, str]:
    capability_rows = (
        ("mock_discovery", "discovery", "search", "discovery.json", 182, 60, 60, None),
        ("mock_metadata", "metadata", "videos", "metadata.json", 124, 169, 168, None),
        (
            "mock_comments",
            "comments",
            "comments",
            "comments.json",
            256,
            60,
            58,
            "Synthetic timeout on page 3",
        ),
        (
            "mock_transcript",
            "transcripts",
            "transcript",
            "transcript.json",
            1020,
            60,
            59,
            None,
        ),
    )
    ids: dict[str, str] = {}
    for index, (
        provider,
        capability,
        endpoint,
        file_name,
        latency,
        requests,
        successes,
        error,
    ) in enumerate(capability_rows):
        fetch_id = demo_id("provider-fetch", capability)
        ids[capability] = fetch_id
        uri, payload_hash = _payload(f"fixtures/demo/raw_payloads/{file_name}")
        started = DEMO_NOW - timedelta(minutes=18 - index * 3)
        session.add(
            ProviderFetch(
                id=fetch_id,
                provider=provider,
                capability=capability,
                endpoint=endpoint,
                request_fingerprint=sha256(f"demo:{provider}:{endpoint}:v1".encode()).hexdigest(),
                started_at=started,
                completed_at=started + timedelta(milliseconds=latency),
                status="partial" if error else "success",
                http_status=206 if error else 200,
                attempt_number=1,
                latency_ms=latency,
                estimated_cost=0.0,
                actual_cost=0.0,
                raw_payload_uri=uri,
                raw_payload_hash=payload_hash,
                parser_version="demo-parser-v1.0.0",
                error_code="demo_partial" if error else None,
                error_message=error,
                linked_entity_ids=[demo_id("video", index)],
            )
        )
        failures = requests - successes
        session.add(
            ProviderHealth(
                provider=provider,
                capability=capability,
                enabled=True,
                priority=1 if index < 2 else 2,
                window_started_at=DEMO_NOW - timedelta(hours=1),
                request_count=requests,
                success_count=successes,
                error_count=failures,
                p50_latency_ms=latency,
                p95_latency_ms=int(latency * (3.36 if latency < 500 else 2.75)),
                estimated_cost=0.0,
                circuit_state="closed",
                last_error=error,
                updated_at=DEMO_NOW - timedelta(minutes=2),
            )
        )
    return ids


def _channel_title(index: int) -> str:
    if index == 0:
        return "Atlas Labs"
    return f"{CHANNEL_PREFIXES[index % 10]} {CHANNEL_SUFFIXES[(index // 10) % 5]}"


def _video_title(topic_index: int, video_index: int) -> str:
    label = str(TOPICS[topic_index]["label"])
    patterns = (
        "{topic}: the end-to-end test",
        "I tried {topic} for seven days",
        "{topic} — setup, cost, and failure cases",
        "What nobody explains about {topic}",
        "{topic}: real workflow benchmark",
        "Before you use {topic}, watch this",
    )
    return patterns[video_index % len(patterns)].format(topic=label)


def _seed_channels(session: Session) -> list[YoutubeChannel]:
    channels: list[YoutubeChannel] = []
    for index in range(50):
        subscribers = 84_000 + ((index * 73_001) % 2_700_000)
        channel = YoutubeChannel(
            id=demo_id("channel", index),
            youtube_channel_id=f"UCESDEMO{index:016d}",
            canonical_url=f"https://www.youtube.com/channel/UCESDEMO{index:016d}",
            title=_channel_title(index),
            description="Synthetic US English AI/technology creator channel for demo mode.",
            country="US",
            default_language="en",
            subscriber_count=subscribers,
            video_count=38 + index * 5,
            view_count=subscribers * (24 + index % 17),
            published_at=DEMO_NOW - timedelta(days=1200 + index * 19),
            last_observed_at=DEMO_NOW - timedelta(minutes=index % 45),
        )
        channels.append(channel)
        session.add(channel)
    return channels


def _seed_videos(
    session: Session,
    channels: list[YoutubeChannel],
    fetch_ids: dict[str, str],
) -> list[YoutubeVideo]:
    videos: list[YoutubeVideo] = []
    snapshots: list[VideoSnapshot] = []
    for index in range(300):
        topic_index = index % len(TOPICS)
        channel = channels[(index * 7 + topic_index) % len(channels)]
        topic = TOPICS[topic_index]
        age_hours = 4 + ((index * 11) % (24 * 21))
        published_at = DEMO_NOW - timedelta(hours=age_hours)
        youtube_id = f"esdemo{index:06d}"
        video = YoutubeVideo(
            id=demo_id("video", index),
            youtube_video_id=youtube_id,
            channel_id=channel.id,
            canonical_url=f"https://www.youtube.com/watch?v={youtube_id}",
            title=_video_title(topic_index, index // 5),
            description=(
                f"Synthetic evidence for {topic['label']}. Demo mode only; no live provider data."
            ),
            published_at=published_at,
            duration_seconds=540 + ((index * 47) % 1320),
            default_language="en",
            category_id="28",
            is_short=False,
            is_live=False,
            thumbnail_url=f"https://i.ytimg.com/vi/{youtube_id}/hqdefault.jpg",
            first_discovered_at=published_at + timedelta(hours=min(age_hours, 7)),
            last_observed_at=DEMO_NOW - timedelta(minutes=index % 22),
        )
        session.add(video)
        videos.append(video)

        base_views = 9_000 + ((index * 17_731) % 620_000)
        growth_multiplier = 1.0 + (4 - topic_index) * 0.16
        for snap_index, fraction in enumerate((0.2, 0.42, 0.68, 1.0)):
            observed_at = published_at + timedelta(hours=age_hours * fraction)
            views = int(base_views * fraction**0.72 * growth_multiplier)
            snapshots.append(
                VideoSnapshot(
                    id=demo_id("snapshot", f"{index}:{snap_index}"),
                    video_id=video.id,
                    observed_at=observed_at,
                    video_age_seconds=int(age_hours * fraction * 3600),
                    view_count=views,
                    like_count=int(views * (0.035 + (index % 5) * 0.004)),
                    comment_count=int(views * (0.0022 + (index % 3) * 0.0007)),
                    views_per_hour=round(views / max(age_hours * fraction, 0.5), 1),
                    snapshot_quality="direct",
                    provider_fetch_id=fetch_ids["metadata"],
                )
            )
    session.flush()
    session.add_all(snapshots)
    return videos


def _angles(topic: dict[str, Any]) -> list[dict[str, Any]]:
    label = str(topic["label"])
    question = str(topic["demand"][1])
    return [
        {
            "title": question,
            "audience_promise": (
                "A grounded answer to the repeated audience question, including "
                "the supported limits and remaining uncertainty."
            ),
            "why_now": "Independent adoption is accelerating before coverage becomes repetitive.",
            "evidence": ["video:0", "video:5", "demand:0"],
            "unanswered_question": question,
            "format": "18–24 minute practical test",
            "effort": "Medium",
            "timing_risk": (
                "A faster channel can take the obvious version of this angle "
                "before production finishes."
            ),
            "title_directions": [
                question,
                f"{label}: supported changes, limits, and open questions",
            ],
            "avoid": "Do not repeat a release-note summary or generic feature list.",
        },
        {
            "title": f"{label}: guardrails, cost, and failure conditions",
            "audience_promise": "A decision guide focused on the risks viewers keep raising.",
            "why_now": "The evidence contains demand that current demos do not resolve.",
            "evidence": ["video:10", "demand:0"],
            "unanswered_question": question,
            "format": "Structured comparison",
            "effort": "Low–medium",
            "timing_risk": "Fast competitors can cover the obvious version first.",
            "title_directions": [
                f"{label}: documented costs and failure conditions",
                f"{label}: who is affected and under which conditions?",
            ],
            "avoid": "Do not quote comments without their stored evidence IDs.",
        },
        {
            "title": f"{label}: adoption conditions for the channel audience",
            "audience_promise": (
                "Clarify when the observed change becomes material to the channel audience."
            ),
            "why_now": "The channel has strong historical fit with practical AI tool tests.",
            "evidence": ["video:15", "video:20", "demand:0"],
            "unanswered_question": question,
            "format": "Challenge / build diary",
            "effort": "High",
            "timing_risk": "Scope must stay small enough to ship on time.",
            "title_directions": [
                f"{label}: when the change becomes material",
                f"{label}: affected users, constraints, and open questions",
            ],
            "avoid": "Do not promise exact future performance.",
        },
    ]


def _demo_opportunities(
    topic: dict[str, Any],
    signal: Signal,
    topic_index: int,
) -> list[dict[str, Any]]:
    fit = float(topic["fit"])
    confidence = "High" if fit >= 80 else "Medium" if fit >= 55 else "Low"
    production_ranges = ((3, 5), (2, 4), (5, 8))
    angles = _angles(topic)
    occupied_pattern = {
        "audience": {"value": "general AI viewers", "share": 0.72},
        "claim": {"value": "summarize the dominant product promise", "share": 0.68},
        "format": {"value": "release explainer", "share": 0.61},
        "context": {"value": "generic feature walkthrough", "share": 0.64},
        "emotion": {"value": "excitement", "share": 0.58},
        "product_anchor": {"value": str(topic["entities"][0]), "share": 0.83},
        "proof_type": {"value": "commentary", "share": 0.66},
        "production_complexity": {"value": "low", "share": 0.59},
    }
    gap_specs = (
        {
            "key": "evidence-led-question",
            "format": "Hands-on test",
            "proof_type": "original test",
            "claim": "test the promise in a reproducible real workflow",
            "complexity": "medium",
            "differentiation": (
                "Most stored coverage explains features; this angle runs one "
                "reproducible workflow and preserves the failure evidence."
            ),
        },
        {
            "key": "failure-boundary",
            "format": "Decision guide",
            "proof_type": "failure evidence",
            "claim": "show where the dominant promise fails",
            "complexity": "low",
            "differentiation": (
                "Current coverage sells the promise; this angle answers the "
                "stored audience question with guardrails and stop conditions."
            ),
        },
        {
            "key": "adoption-conditions",
            "format": "Case study",
            "proof_type": "before-and-after proof",
            "claim": "apply the promise under real channel constraints",
            "complexity": "high",
            "differentiation": (
                "The evidence is generic; this angle uses Atlas Labs’ production "
                "constraints and a measured before-and-after result."
            ),
        },
    )
    for angle_index, angle in enumerate(angles):
        production_min, production_max = production_ranges[angle_index]
        gap_spec = gap_specs[angle_index]
        ranking_score = round(91.0 - angle_index * 6.5 - topic_index * 0.7, 1)
        feasibility = assess_production_feasibility(
            observed_at=DEMO_NOW,
            opportunity_end=signal.opportunity_end,
            workspace_timezone="America/Los_Angeles",
            lifecycle_stage=signal.lifecycle_stage,
            adoption_rate=float(topic["components"].momentum),
            large_channel_entry=signal.lifecycle_stage in {"Mass Market", "Saturated", "Declining"},
            production_days_min=production_min,
            production_days_max=production_max,
            team_size=3,
            research_capacity_hours=18,
            filming_required=False,
            external_guests_required=False,
            editing_complexity="medium",
            has_product_access=True,
            requires_product_access=angle_index in {0, 2},
            weekday_publish_only=True,
            content_calendar=[],
        )
        angle.update(
            {
                "opportunity_id": demo_id(
                    "opportunity",
                    f"{topic_index}:{angle_index}",
                ),
                "rank": angle_index + 1,
                "status": "active",
                "channel_fit_score": fit,
                "opportunity_confidence": confidence,
                "best_publish_window": {
                    "start": signal.opportunity_start.isoformat(),
                    "end": signal.opportunity_end.isoformat(),
                    "label": (
                        f"{max(0, (signal.opportunity_start - DEMO_NOW).days)}–"
                        f"{max(0, (signal.opportunity_end - DEMO_NOW).days)} days"
                    ),
                },
                "expected_breakout_window": {
                    "start": signal.opportunity_start.isoformat(),
                    "end": signal.opportunity_end.isoformat(),
                },
                "expected_saturation_window": {
                    "start": signal.opportunity_end.isoformat(),
                    "end": (signal.opportunity_end + timedelta(days=7)).isoformat(),
                },
                "production_time_days": {
                    "min": feasibility.estimated_days_min,
                    "max": feasibility.estimated_days_max,
                },
                "recommended_publish_by": (feasibility.recommended_publish_by.isoformat()),
                "recommended_publish_by_label": (feasibility.recommended_publish_by_label),
                "feasibility": feasibility.feasibility,
                "feasible_for_act": feasibility.feasible_for_act,
                "infeasibility_reasons": list(feasibility.reason_codes),
                "decay_days": feasibility.decay_days,
                "decay_version": feasibility.version,
                "timezone": feasibility.timezone,
                "fit_reasons": [
                    f"topical relevance: {max(42, int(fit) + 2)}/100",
                    f"audience overlap: {max(40, int(fit) - 1)}/100",
                    f"production feasibility: {84 - topic_index * 6}/100",
                ],
                "gap_key": gap_spec["key"],
                "release_ready": angle_index == 0,
                "insight_status": ("evidence_backed" if angle_index == 0 else "candidate"),
                "insight_type": (
                    "audience_demand" if angle_index == 0 else "coverage_gap_candidate"
                ),
                "insight_statement": (
                    (
                        "The same unresolved audience question appears across "
                        "independent stored evidence: "
                        f"{angle['unanswered_question']}"
                    )
                    if angle_index == 0
                    else (
                        "The stored evidence does not yet establish a non-obvious "
                        "insight for this coverage-gap hypothesis."
                    )
                ),
                "insight_reason_codes": (
                    [
                        "confirmed_cross_video_audience_demand",
                    ]
                    if angle_index == 0
                    else [
                        "coverage_gap_only",
                        "no_confirmed_demand_or_performance_split",
                    ]
                ),
                "insight_evidence": list(angle["evidence"]),
                "insight_metrics": {
                    "pattern_sample_size": 8,
                    "demand_supported": angle_index == 0,
                },
                "occupied_pattern": occupied_pattern,
                "open_gap": {
                    "audience": "Atlas Labs’ practical AI audience",
                    "claim": gap_spec["claim"],
                    "format": gap_spec["format"],
                    "context": "owned channel workflow",
                    "proof_type": gap_spec["proof_type"],
                    "production_complexity": gap_spec["complexity"],
                    "is_open": True,
                },
                "differentiation": gap_spec["differentiation"],
                "ranking_score": ranking_score,
                "score_components": {
                    "unmet_demand_strength": 90.0,
                    "content_gap_strength": 96.0 - angle_index * 5,
                    "channel_fit": fit,
                    "production_feasibility": 84.0 - topic_index * 6,
                    "timing": 86.0 - topic_index * 5,
                    "evidence_strength": 88.0,
                    "novelty": 82.0 if angle_index == 0 else 42.0,
                    "brand_risk": 0.0,
                },
                "content_gap_version": "content-gap-v4",
                "opportunity_ranking_version": "opportunity-ranking-v5",
                **(
                    {
                        "why_primary": (
                            "Primary because it combines the strongest open content "
                            "cell, original proof, channel fit, and publishability."
                        )
                    }
                    if angle_index == 0
                    else {
                        "why_ranked_below_primary": (
                            "Useful alternative, but its combined gap, production, "
                            "or timing score is lower than the primary opportunity."
                        )
                    }
                ),
            }
        )
    return angles


def _seed_topics_and_signals(
    session: Session,
    channels: list[YoutubeChannel],
    videos: list[YoutubeVideo],
    fetch_ids: dict[str, str],
) -> list[Signal]:
    signals: list[Signal] = []
    for topic_index, topic_data in enumerate(TOPICS):
        topic_id = demo_id("topic", topic_index)
        first_seen = DEMO_NOW - timedelta(days=int(topic_data["first_seen_days"]))
        topic = Topic(
            id=topic_id,
            canonical_label=str(topic_data["label"]),
            aliases_json=list(topic_data["aliases"]),
            entities_json=list(topic_data["entities"]),
            first_observed_at=first_seen,
            first_confirmed_at=first_seen + timedelta(days=2),
            lifecycle_stage=str(topic_data["stage"]),
            status="active",
            source_kind="demo",
            merged_into_topic_id=None,
            clustering_version="demo-microtopic-v5",
            identity_json={
                "domain": str(topic_data["category"]),
                "facet": "applied_workflows",
                "primary_entity": str(topic_data["entities"][0]),
                "secondary_entities": list(topic_data["entities"][1:]),
                "audience": "AI and technology creators",
                "user_problem": str(topic_data["demand"][0]),
                "core_claim": str(topic_data["thesis"]),
                "workflow_context": "creator coverage decision",
                "format_distribution": {
                    "release explainer": 0.61,
                    "tutorial": 0.24,
                    "comparison": 0.15,
                },
            },
            specificity_score=(88.0 if str(topic_data["confidence"]) == "High" else 80.0),
            thesis_support_ratio=(0.92 if str(topic_data["confidence"]) == "High" else 0.84),
            visibility_reason_codes_json=["identity_supported", "demo_evidence"],
        )
        session.add(topic)
        session.flush()

        topic_videos = [video for index, video in enumerate(videos) if index % 5 == topic_index]
        evidence_videos = sorted(topic_videos, key=lambda item: item.published_at, reverse=True)[
            :12
        ]
        for membership_index, video in enumerate(evidence_videos):
            session.add(
                TopicVideoMembership(
                    topic_id=topic_id,
                    video_id=video.id,
                    membership_score=round(0.99 - membership_index * 0.018, 3),
                    assignment_method="demo_entity_embedding",
                    evidence_role=(
                        "driver"
                        if membership_index < 2
                        else "amplifier"
                        if membership_index < 5
                        else "supporting"
                    ),
                    assigned_at=video.first_discovered_at,
                )
            )
        for pattern_index, video in enumerate(evidence_videos[:3]):
            pattern_key = demo_id(
                "content-pattern-key",
                f"{topic_index}:{pattern_index}",
            )
            session.add(
                TopicContentPattern(
                    id=demo_id(
                        "content-pattern",
                        f"{topic_index}:{pattern_index}",
                    ),
                    topic_id=topic_id,
                    video_id=video.id,
                    pattern_key=pattern_key,
                    pattern_json={
                        "video_id": video.id,
                        "audience": "general AI viewers",
                        "claim": "summarize the dominant product promise",
                        "format": "release explainer",
                        "context": "generic feature walkthrough",
                        "emotion": "excitement",
                        "product_anchor": str(topic_data["entities"][0]),
                        "proof_type": "commentary",
                        "production_complexity": "low",
                        "pattern_key": pattern_key,
                        "evidence_refs": [f"video:{video.id}"],
                    },
                    evidence_json=[f"video:{video.id}"],
                    model_version="topic-content-pattern-v1",
                    calculated_at=DEMO_NOW - timedelta(minutes=20),
                )
            )

        score_components = topic_data["components"]
        assert isinstance(score_components, ScoreComponents)
        confidence = str(topic_data["confidence"])
        evidence_quality = (
            {
                "baseline_coverage": 92.0,
                "transcript_coverage": 84.0,
                "specificity_score": 88.0,
            }
            if confidence == "High"
            else {
                "baseline_coverage": 76.0,
                "transcript_coverage": 68.0,
                "specificity_score": 80.0,
            }
        )
        component_json = {
            **score_components.normalized().__dict__,
            **evidence_quality,
        }
        score = calculate_early_signal_score(score_components)
        window_start, window_end = topic_data["window"]
        signal = Signal(
            id=demo_id("signal", topic_index),
            topic_id=topic_id,
            status="active",
            source_kind="demo",
            lifecycle_stage=str(topic_data["stage"]),
            score=score,
            confidence=confidence,
            opportunity_start=DEMO_NOW + timedelta(days=int(window_start)),
            opportunity_end=DEMO_NOW + timedelta(days=int(window_end)),
            thesis=str(topic_data["thesis"]),
            why_emerging_json=list(topic_data["why"]),
            component_json=component_json,
            evidence_version="demo-evidence-v1",
            generated_at=DEMO_NOW - timedelta(minutes=18 + topic_index * 7),
            expires_at=DEMO_NOW + timedelta(days=max(int(window_end), 2)),
        )
        signals.append(signal)
        session.add(signal)
        session.flush()
        opportunities = _demo_opportunities(
            topic_data,
            signal,
            topic_index,
        )
        for opportunity in opportunities:
            opportunity["evidence"] = [f"video:{video.id}" for video in evidence_videos[:3]]
            opportunity["insight_evidence"] = list(opportunity["evidence"])
        workspace_score = WorkspaceSignalScore(
            workspace_id=DEMO_WORKSPACE_ID,
            signal_id=signal.id,
            channel_id=DEMO_OWNED_CHANNEL_ID,
            channel_fit_score=float(topic_data["fit"]),
            fit_component_json={
                "topical_relevance": max(42, int(topic_data["fit"]) + 2),
                "audience_overlap": max(40, int(topic_data["fit"]) - 1),
                "format_compatibility": max(40, int(topic_data["fit"]) - 3),
                "authority_or_credibility": max(38, int(topic_data["fit"]) - 4),
                "production_feasibility": 84 - topic_index * 6,
                "historical_performance_similarity": max(38, int(topic_data["fit"]) - 6),
                "timing_feasibility": 82 - topic_index * 5,
                "cannibalization_penalty": topic_index * 3,
                "brand_risk_penalty": 0,
                "fit_version": "channel-fit-v1",
                "profile_source": "demo",
                "explanation": (
                    "Atlas Labs performs best on practical AI tool tests with original "
                    "evidence and can publish within this window."
                ),
            },
            recommended_angle_json=opportunities,
            fit_version="channel-fit-v1",
            calculated_at=DEMO_NOW - timedelta(minutes=15),
        )
        session.add(workspace_score)
        for opportunity in opportunities:
            session.add(
                TopicContentGap(
                    id=demo_id(
                        "content-gap",
                        f"{topic_index}:{opportunity['gap_key']}",
                    ),
                    workspace_id=DEMO_WORKSPACE_ID,
                    topic_id=topic_id,
                    gap_key=str(opportunity["gap_key"]),
                    rank=int(opportunity["rank"]),
                    status="active",
                    occupied_pattern_json=dict(opportunity["occupied_pattern"]),
                    open_gap_json=dict(opportunity["open_gap"]),
                    score_components_json=dict(opportunity["score_components"]),
                    evidence_json=list(opportunity["evidence"]),
                    model_version="content-gap-v4",
                    ranking_version="opportunity-ranking-v5",
                    calculated_at=DEMO_NOW - timedelta(minutes=15),
                )
            )
        ensure_signal_review(session, DEMO_WORKSPACE_ID, signal)

        topic_snapshots: list[TopicSnapshot] = []
        for point in range(8):
            observed = first_seen + (DEMO_NOW - first_seen) * ((point + 1) / 8)
            stage_factor = (topic_index + 1) * 0.8
            growth = (point + 1) ** (1.15 if topic_index < 3 else 0.8)
            topic_snapshot = TopicSnapshot(
                id=demo_id("topic-snapshot", f"{topic_index}:{point}"),
                topic_id=topic_id,
                observed_at=observed,
                video_count_24h=max(1, int(growth + 5 - stage_factor)),
                video_count_72h=max(2, int(growth * 2.4 + topic_index)),
                distinct_channels_72h=max(2, int(growth * 1.7)),
                aggregate_view_velocity=round(950 * growth * (1.2 - topic_index * 0.08), 1),
                median_outlier_ratio=round(1.3 + growth * 0.18, 2),
                large_channel_count=int(point * topic_index / 4),
                demand_score=float(component_json["audience_demand"]),
                saturation_score=float(component_json["saturation_penalty"]),
                fragility_score=float(component_json["fragility_penalty"]),
                component_json={"momentum_index": round(growth * 11.5, 1)},
            )
            topic_snapshots.append(topic_snapshot)
            session.add(topic_snapshot)

        current_stage = str(topic_data["stage"])
        stage_sequence = ["Seed"]
        if current_stage in {"Emerging", "Breakout", "Mass Market", "Saturated"}:
            stage_sequence.append("Emerging")
        if current_stage in {"Breakout", "Mass Market", "Saturated"}:
            stage_sequence.append("Breakout")
        if current_stage in {"Mass Market", "Saturated"}:
            stage_sequence.append("Mass Market")
        if current_stage == "Saturated":
            stage_sequence.append("Saturated")
        stage_snapshot_index = {
            "Seed": 0,
            "Emerging": 3,
            "Breakout": 5,
            "Mass Market": 6,
            "Saturated": 7,
        }
        stage_times: dict[str, datetime] = {}
        previous_stage: str | None = None
        for stage in stage_sequence:
            lifecycle_snapshot = topic_snapshots[stage_snapshot_index[stage]]
            stage_times[stage] = lifecycle_snapshot.observed_at
            session.add(
                TopicLifecycleTransition(
                    id=demo_id(
                        "topic-lifecycle-transition",
                        f"{topic_index}:{stage}",
                    ),
                    topic_id=topic_id,
                    from_stage=previous_stage,
                    to_stage=stage,
                    transitioned_at=lifecycle_snapshot.observed_at,
                    measurement_id=lifecycle_snapshot.id,
                    score=score if stage == current_stage else None,
                    reason_codes_json=["demo_fixture", "stored_topic_measurement"],
                    history_version=HISTORY_VERSION,
                    created_at=DEMO_NOW,
                )
            )
            previous_stage = stage

        first_large_snapshot = next(
            (
                lifecycle_snapshot
                for lifecycle_snapshot in topic_snapshots
                if lifecycle_snapshot.large_channel_count > 0
            ),
            None,
        )
        first_visible_stage = "Emerging" if "Emerging" in stage_times else "Seed"
        first_visible_snapshot = topic_snapshots[stage_snapshot_index[first_visible_stage]]
        first_published_video = min(
            evidence_videos,
            key=lambda item: item.published_at,
        )
        first_discovered_video = min(
            evidence_videos,
            key=lambda item: item.first_discovered_at,
        )
        session.add(
            TopicLifecycleSummary(
                topic_id=topic_id,
                first_video_published_at=first_published_video.published_at,
                first_discovered_at=first_discovered_video.first_discovered_at,
                first_topic_formed_at=topic_snapshots[0].observed_at,
                first_seed_at=stage_times.get("Seed"),
                first_emerging_at=stage_times.get("Emerging"),
                first_signal_visible_at=first_visible_snapshot.observed_at,
                first_breakout_at=stage_times.get("Breakout"),
                first_mass_market_at=stage_times.get("Mass Market"),
                first_saturated_at=stage_times.get("Saturated"),
                first_declining_at=None,
                first_large_channel_adoption_at=(
                    first_large_snapshot.observed_at if first_large_snapshot is not None else None
                ),
                latest_measurement_at=topic_snapshots[-1].observed_at,
                evidence_json={
                    "first_video_id": first_published_video.id,
                    "first_discovered_video_id": first_discovered_video.id,
                    "first_topic_measurement_id": topic_snapshots[0].id,
                    "first_signal_visible_measurement_id": first_visible_snapshot.id,
                    "first_large_channel_measurement_id": (
                        first_large_snapshot.id if first_large_snapshot is not None else None
                    ),
                    "large_channel_threshold_subscribers": 100_000,
                    "history_version": HISTORY_VERSION,
                },
                backfill_version=BACKFILL_VERSION,
                created_at=DEMO_NOW,
                updated_at=DEMO_NOW,
            )
        )

        cluster_id = demo_id("demand-cluster", topic_index)
        demand_label, demand_question = topic_data["demand"]
        cluster = DemandCluster(
            id=cluster_id,
            topic_id=topic_id,
            label=str(demand_label),
            summary=(
                f"Viewers repeatedly ask: {demand_question} Evidence spans independent "
                "channels and recent videos."
            ),
            taxonomy="test_or_proof_request" if topic_index == 4 else "explicit_question",
            comment_count=128 + topic_index * 19,
            distinct_commenter_count=110 + topic_index * 17,
            distinct_video_count=8 + topic_index,
            distinct_channel_count=7 + topic_index,
            demand_score=float(component_json["audience_demand"]),
            first_observed_at=first_seen + timedelta(days=1),
            last_observed_at=DEMO_NOW - timedelta(hours=topic_index + 1),
            model_version="demo-rules-v1",
            visibility_status="user_visible",
            evidence_strength="Strong",
            median_relevance_score=0.91,
            high_actionability_count=3,
            relevance_model_version=RELEVANCE_MODEL_VERSION,
        )
        session.add(cluster)
        session.flush()
        snippets = (
            str(demand_question),
            f"Can you show a real failure case for {topic_data['label']}?",
            f"What does the setup cost for {topic_data['label']} in practice?",
        )
        for comment_index, text in enumerate(snippets):
            video = evidence_videos[comment_index]
            comment_id = demo_id("comment", f"{topic_index}:{comment_index}")
            normalized_hash = sha256(" ".join(text.lower().split()).encode()).hexdigest()
            session.add(
                YoutubeComment(
                    id=comment_id,
                    provider_comment_id=f"demo-{topic_index}-{comment_index}",
                    video_id=video.id,
                    parent_comment_id=None,
                    text=text,
                    published_at=DEMO_NOW - timedelta(hours=4 + comment_index * 7),
                    like_count=214 - comment_index * 43 + topic_index * 7,
                    reply_count=18 - comment_index * 4,
                    is_reply=False,
                    language="en",
                    normalized_hash=normalized_hash,
                    provider_fetch_id=fetch_ids["comments"],
                )
            )
            session.flush()
            relevance_id = demo_id(
                "comment-topic-relevance",
                f"{topic_index}:{comment_index}",
            )
            input_hash = sha256(
                f"{comment_id}:{topic_id}:{video.id}:{RELEVANCE_MODEL_VERSION}".encode()
            ).hexdigest()
            relevance = CommentTopicRelevance(
                id=relevance_id,
                comment_id=comment_id,
                topic_id=topic_id,
                video_id=video.id,
                is_relevant=True,
                relevance_score=round(0.94 - comment_index * 0.03, 4),
                comment_topic_semantic_similarity=round(
                    0.88 - comment_index * 0.03,
                    4,
                ),
                comment_video_semantic_similarity=round(
                    0.9 - comment_index * 0.03,
                    4,
                ),
                entity_overlap_score=0.9,
                claim_support_score=0.92,
                intent_actionability_score=1.0,
                duplicate_or_echo_probability=0.0,
                spam_probability=0.01,
                intent=("test_or_proof_request" if topic_index == 4 else "explicit_question"),
                actionability="high",
                supported_entities_json=list(topic_data["entities"])[:2],
                supported_claims_json=["stored_demo_claim"],
                reason_codes_json=[
                    "entity_match",
                    "video_claim_match",
                    "high_actionability",
                    "accepted",
                ],
                evidence_json={
                    "source_kind": "demo",
                    "topic_id": topic_id,
                    "video_id": video.id,
                    "comment_id": comment_id,
                },
                model_version=RELEVANCE_MODEL_VERSION,
                input_hash=input_hash,
                override_decision=None,
                override_reason=None,
                reviewer_id=None,
                reviewed_at=None,
                calculated_at=DEMO_NOW,
                updated_at=DEMO_NOW,
            )
            session.add(relevance)
            session.flush()
            session.add(
                CommentTopicRelevanceEvent(
                    id=demo_id(
                        "comment-topic-relevance-event",
                        f"{topic_index}:{comment_index}",
                    ),
                    relevance_id=relevance_id,
                    topic_id=topic_id,
                    comment_id=comment_id,
                    event_type="classified",
                    previous_result_json={},
                    result_json={
                        "is_relevant": True,
                        "effective_relevant": True,
                        "relevance_score": relevance.relevance_score,
                        "model_version": RELEVANCE_MODEL_VERSION,
                    },
                    actor_id=None,
                    note="Deterministic demo relevance evidence.",
                    idempotency_key=(
                        f"demo-comment-topic-relevance:{relevance_id}:{RELEVANCE_MODEL_VERSION}"
                    ),
                    model_version=RELEVANCE_MODEL_VERSION,
                    created_at=DEMO_NOW,
                )
            )
            session.add(
                DemandClusterComment(
                    demand_cluster_id=cluster_id,
                    comment_id=comment_id,
                    membership_score=0.96 - comment_index * 0.05,
                    is_representative=True,
                )
            )

        for transcript_index, video in enumerate(evidence_videos[:2]):
            text = (
                f"This demo transcript segment examines {topic_data['label']}, including "
                f"the real workflow, limitations, cost, and the question: {demand_question}"
            )
            transcript_id = demo_id("transcript", f"{topic_index}:{transcript_index}")
            session.add(
                VideoTranscript(
                    id=transcript_id,
                    video_id=video.id,
                    language="en",
                    transcript_type="native",
                    provider="mock_transcript",
                    provider_fetch_id=fetch_ids["transcripts"],
                    full_text=text,
                    content_hash=sha256(text.encode()).hexdigest(),
                    quality_score=0.97 - transcript_index * 0.03,
                    generated_cost=0.0,
                    fetched_at=DEMO_NOW - timedelta(hours=2),
                    summary_json={"text": text, "method": "extractive"},
                    entities_json=list(topic_data["entities"]),
                    key_claims_json=[
                        {
                            "text": text,
                            "start_seconds": 0,
                            "end_seconds": 18,
                        }
                    ],
                    use_cases_json=[text],
                    comparisons_json=[],
                    unanswered_questions_json=[demand_question],
                    narrative_angle="problem-solution",
                    content_format="explainer",
                    processing_version="transcript-processing-v2",
                )
            )
            session.flush()
            session.add(
                TranscriptSegment(
                    id=demo_id("transcript-segment", f"{topic_index}:{transcript_index}"),
                    transcript_id=transcript_id,
                    position=0,
                    start_seconds=0,
                    end_seconds=18,
                    text=text,
                    embedding_json=[],
                    is_evidence=True,
                    segment_hash=sha256(f"0:18:{text}".encode()).hexdigest(),
                )
            )

        session.add(
            FieldProvenance(
                id=demo_id("provenance", f"signal:{topic_index}:score"),
                entity_type="signal",
                entity_id=signal.id,
                field_name="score",
                provider_fetch_id=fetch_ids["metadata"],
                observed_at=DEMO_NOW - timedelta(minutes=20),
                confidence=1.0,
                value_hash=sha256(str(score).encode()).hexdigest(),
            )
        )
    return signals


def seed_demo(session: Session) -> None:
    settings = get_settings()
    if not settings.demo_mode:
        raise RuntimeError("Demo reset is allowed only when DEMO_MODE=true")

    _clear_demo(session)
    if session.get(User, DEMO_USER_ID) is None:
        session.add(
            User(
                id=DEMO_USER_ID,
                email="demo@earlysignal.local",
                name="Avery Chen",
                created_at=DEMO_NOW - timedelta(days=30),
            )
        )
    if session.get(Workspace, DEMO_WORKSPACE_ID) is None:
        session.add(
            Workspace(
                id=DEMO_WORKSPACE_ID,
                name="Atlas Labs",
                slug="atlas-labs",
                plan="private_beta_demo",
                timezone="America/Los_Angeles",
                created_at=DEMO_NOW - timedelta(days=30),
            )
        )
    if session.get(WorkspaceMember, (DEMO_WORKSPACE_ID, DEMO_USER_ID)) is None:
        session.add(
            WorkspaceMember(
                workspace_id=DEMO_WORKSPACE_ID,
                user_id=DEMO_USER_ID,
                role="owner",
            )
        )
    onboarding = session.get(WorkspaceOnboarding, DEMO_WORKSPACE_ID)
    if onboarding is None:
        session.add(
            WorkspaceOnboarding(
                workspace_id=DEMO_WORKSPACE_ID,
                status="completed",
                current_step=6,
                completed_steps_json=[
                    "workspace",
                    "owned_channel",
                    "channel_profile",
                    "reference_channels",
                    "topic_universe",
                    "digest",
                ],
                completed_at=DEMO_NOW - timedelta(days=20),
                created_at=DEMO_NOW - timedelta(days=30),
                updated_at=DEMO_NOW - timedelta(days=1),
            )
        )
    fetch_ids = _seed_provider_operations(session)
    channels = _seed_channels(session)
    session.flush()
    session.add(
        WorkspaceChannel(
            workspace_id=DEMO_WORKSPACE_ID,
            channel_id=DEMO_OWNED_CHANNEL_ID,
            relationship="owned",
            priority=0,
            active=True,
        )
    )
    session.add(
        ChannelProfile(
            workspace_id=DEMO_WORKSPACE_ID,
            channel_id=DEMO_OWNED_CHANNEL_ID,
            profile_source="demo",
            audience_description=(
                "English-speaking builders and technical creators who want practical, "
                "evidence-backed AI workflows."
            ),
            geography="US",
            language="en",
            topic_keywords_json=[
                "AI agents",
                "developer tools",
                "automation",
                "local AI",
                "creator workflows",
            ],
            preferred_formats_json=[
                "Evidence-led explainer",
                "Hands-on test",
                "Structured comparison",
            ],
            creator_expertise_json=[
                "software engineering",
                "AI tools",
                "workflow automation",
                "technical testing",
            ],
            production_capabilities_json=[
                "screen recording",
                "software testing",
                "technical explanation",
            ],
            exclusions_json=["crypto promotion", "unverified medical claims"],
            strategic_goals_json=[
                "grow authority in practical AI engineering",
                "publish original tests before mass-market coverage",
            ],
            title_style_json={
                "voice": "specific, practical, skeptical",
                "patterns": ["I tested {topic}", "{topic}: what actually works"],
            },
            normal_duration_min_seconds=14 * 60,
            normal_duration_max_seconds=24 * 60,
            production_days_min=4,
            production_days_max=7,
            core_topics_json=[
                "AI agents",
                "developer tools",
                "automation",
                "local AI",
            ],
            adjacent_topics_json=["creator workflows", "AI video"],
            legacy_topics_json=["generic productivity apps"],
            successful_formats_json=["Hands-on test", "Structured comparison"],
            upload_cadence_json={
                "median_days_between_uploads": 5.0,
                "uploads_per_month": 6.0,
                "sample_size": 24,
                "method": "weighted-history-v2",
            },
            audience_sophistication="advanced",
            creator_authority="expert",
            risk_tolerance="balanced",
            team_size=3,
            research_capacity_hours=18,
            filming_required=False,
            external_guests_required=False,
            editing_complexity="medium",
            access_to_products_json=["AI software", "developer tools", "local GPUs"],
            experiment_level="balanced",
            evergreen_trend_balance=0.35,
            weekday_publish_only=True,
            content_calendar_json=[],
            inference_json={
                "version": "channel-profile-v2",
                "source": "deterministic-demo-history",
            },
            explicit_overrides_json={
                "strategic_goals": [
                    "grow authority in practical AI engineering",
                    "publish original tests before mass-market coverage",
                ],
                "production_days_min": 4,
                "production_days_max": 7,
                "team_size": 3,
                "risk_tolerance": "balanced",
            },
            profile_version="channel-profile-v2",
            created_at=DEMO_NOW - timedelta(days=30),
            updated_at=DEMO_NOW - timedelta(days=1),
        )
    )
    for channel in channels[1:13]:
        session.add(
            WorkspaceChannel(
                workspace_id=DEMO_WORKSPACE_ID,
                channel_id=channel.id,
                relationship="competitor",
                priority=1,
                active=True,
            )
        )
    for channel in channels[:8]:
        session.add(
            ChannelBaseline(
                id=demo_id("baseline", channel.id),
                channel_id=channel.id,
                window="7d",
                metric_name="median_views",
                metric_value=round(channel.subscriber_count * 0.18, 1),
                sample_size=18,
                calculated_at=DEMO_NOW - timedelta(hours=2),
                version="demo-v1",
            )
        )
    videos = _seed_videos(session, channels, fetch_ids)
    session.flush()
    signals = _seed_topics_and_signals(session, channels, videos, fetch_ids)
    session.flush()

    session.add(
        SignalAction(
            id=demo_id("signal-action", "saved"),
            workspace_id=DEMO_WORKSPACE_ID,
            signal_id=signals[2].id,
            user_id=DEMO_USER_ID,
            action="save",
            reason="strong_fit",
            created_at=DEMO_NOW - timedelta(days=1),
        )
    )
    session.add(
        SignalAction(
            id=demo_id("signal-action", "dismissed"),
            workspace_id=DEMO_WORKSPACE_ID,
            signal_id=signals[4].id,
            user_id=DEMO_USER_ID,
            action="dismiss",
            reason="too_late",
            created_at=DEMO_NOW - timedelta(days=2),
        )
    )
    brief_id = demo_id("brief", "published-demo")
    suggested_brief_id = demo_id("brief", "outcome-suggestion-demo")
    session.add(
        ContentBrief(
            id=brief_id,
            workspace_id=DEMO_WORKSPACE_ID,
            signal_id=signals[1].id,
            channel_id=DEMO_OWNED_CHANNEL_ID,
            opportunity_id=demo_id("opportunity", "1:0"),
            evidence_version="demo-evidence-v1:channel-fit-v1",
            status="published",
            title="Can an AI browser agent buy the right laptop?",
            brief_json=_demo_opportunities(TOPICS[1], signals[1], 1)[0],
            created_at=DEMO_NOW - timedelta(days=9),
            updated_at=DEMO_NOW - timedelta(days=2),
        )
    )
    session.add(
        ContentBrief(
            id=suggested_brief_id,
            workspace_id=DEMO_WORKSPACE_ID,
            signal_id=signals[0].id,
            channel_id=DEMO_OWNED_CHANNEL_ID,
            opportunity_id=demo_id("opportunity", "0:0"),
            evidence_version="demo-evidence-v1:channel-fit-v1",
            status="approved",
            title="I tested Claude Code autonomous workflows end to end",
            brief_json=_demo_opportunities(TOPICS[0], signals[0], 0)[0],
            created_at=DEMO_NOW - timedelta(days=3),
            updated_at=DEMO_NOW - timedelta(hours=12),
        )
    )
    session.add(
        OutcomeSuggestion(
            id=demo_id("outcome-suggestion", "pending-demo"),
            workspace_id=DEMO_WORKSPACE_ID,
            video_id=videos[0].id,
            signal_id=signals[0].id,
            suggested_brief_id=suggested_brief_id,
            selected_brief_id=None,
            outcome_id=None,
            status="suggested",
            match_confidence=0.86,
            reason_codes_json=[
                "title_overlap",
                "description_or_topic_overlap",
                "published_after_active_brief",
            ],
            match_features_json={
                "title_similarity": 0.72,
                "evidence_coverage": 0.88,
                "brief_title_coverage": 0.81,
                "days_from_brief": 2.83,
            },
            baseline_json={
                "version": "outcome-metrics-v2",
                "sample_size": 5,
                "minimum_stable_sample_size": 5,
                "stability": "stable",
                "video_ids": [videos[index].id for index in (50, 100, 150, 200, 250)],
                "filters": {
                    "content_type": "long",
                    "duration_ratio": "0.6–1.6x",
                    "topic_family": "title-token similarity ranked",
                    "upload_period_days": 180,
                    "sponsored": False,
                },
                "views_24h": 98500,
                "sample_size_24h": 5,
                "stability_24h": "stable",
                "views_72h": 131000,
                "sample_size_72h": 5,
                "stability_72h": "stable",
                "views_7d": 176000,
                "sample_size_7d": 5,
                "stability_7d": "stable",
                "views_30d": None,
                "sample_size_30d": 0,
                "stability_30d": "early",
            },
            metrics_json={},
            model_version="outcome-association-v1",
            detected_at=DEMO_NOW - timedelta(hours=1),
            decided_at=None,
            created_at=DEMO_NOW - timedelta(hours=1),
            updated_at=DEMO_NOW - timedelta(hours=1),
        )
    )
    session.add(
        PublishedOutcome(
            id=demo_id("outcome", "published-demo"),
            workspace_id=DEMO_WORKSPACE_ID,
            signal_id=signals[1].id,
            content_brief_id=brief_id,
            youtube_video_id="esoutcome001",
            published_at=DEMO_NOW - timedelta(days=2),
            baseline_definition=(
                "Median performance of eight comparable owned uploads: long-form, "
                "similar duration, topic-family proximity, and published during "
                "the previous six months."
            ),
            performance_json={
                "version": "outcome-metrics-v2",
                "interpretation": "associated_uplift_not_causal",
                "views_24h": 284000,
                "baseline_views_24h": 142000,
                "channel_relative_uplift_24h": 2.0,
                "views_7d": None,
                "baseline_views_7d": None,
                "channel_relative_uplift_7d": None,
                "comparator": {
                    "version": "outcome-metrics-v2",
                    "sample_size": 8,
                    "minimum_stable_sample_size": 5,
                    "stability": "stable",
                    "video_ids": [
                        videos[index].id for index in (25, 50, 75, 100, 150, 200, 250, 275)
                    ],
                    "filters": {
                        "content_type": "long",
                        "duration_ratio": "0.6–1.6x",
                        "topic_family": "title-token similarity ranked",
                        "upload_period_days": 180,
                        "sponsored": False,
                    },
                    "views_24h": 142000,
                    "sample_size_24h": 8,
                    "stability_24h": "stable",
                    "views_72h": None,
                    "sample_size_72h": 0,
                    "stability_72h": "early",
                    "views_7d": None,
                    "sample_size_7d": 0,
                    "stability_7d": "early",
                    "views_30d": None,
                    "sample_size_30d": 0,
                    "stability_30d": "early",
                },
            },
            success_status="successful",
            user_notes="Reached 284K views during the first 24 hours.",
            metrics_version="outcome-metrics-v2",
            created_at=DEMO_NOW - timedelta(days=2),
        )
    )
    for day in range(7):
        observed_at = DEMO_NOW - timedelta(days=6 - day, hours=2)
        for impression in range(4 + day):
            signal = signals[(day + impression) % len(signals)]
            record_product_event(
                session,
                workspace_id=DEMO_WORKSPACE_ID,
                event_type="signal_impression",
                event_key=f"demo:impression:{day}:{impression}",
                signal_id=signal.id,
                metadata={"surface": "signal_feed", "data_mode": "demo"},
                occurred_at=observed_at + timedelta(minutes=impression),
            )
        for opened in range(1 + day % 3):
            signal = signals[(day + opened) % len(signals)]
            record_product_event(
                session,
                workspace_id=DEMO_WORKSPACE_ID,
                event_type="signal_open",
                event_key=f"demo:open:{day}:{opened}",
                signal_id=signal.id,
                metadata={"surface": "signal_detail", "data_mode": "demo"},
                occurred_at=observed_at + timedelta(minutes=30 + opened),
            )
    record_product_event(
        session,
        workspace_id=DEMO_WORKSPACE_ID,
        event_type="signal_saved",
        event_key="demo:action:saved",
        signal_id=signals[2].id,
        metadata={"reason": "strong_fit"},
        occurred_at=DEMO_NOW - timedelta(days=1),
    )
    record_product_event(
        session,
        workspace_id=DEMO_WORKSPACE_ID,
        event_type="signal_dismissed",
        event_key="demo:action:dismissed",
        signal_id=signals[4].id,
        metadata={"reason": "too_late"},
        occurred_at=DEMO_NOW - timedelta(days=2),
    )
    record_product_event(
        session,
        workspace_id=DEMO_WORKSPACE_ID,
        event_type="brief_created",
        event_key="demo:brief:published",
        signal_id=signals[1].id,
        content_brief_id=brief_id,
        metadata={"title": "Can an AI browser agent buy the right laptop?"},
        occurred_at=DEMO_NOW - timedelta(days=9),
    )
    record_product_event(
        session,
        workspace_id=DEMO_WORKSPACE_ID,
        event_type="outcome_successful",
        event_key="demo:outcome:published",
        signal_id=signals[1].id,
        content_brief_id=brief_id,
        outcome_id=demo_id("outcome", "published-demo"),
        metadata={"youtube_video_id": "esoutcome001", "success_status": "successful"},
        occurred_at=DEMO_NOW - timedelta(days=2),
    )
    subscription = session.get(DigestSubscription, DEMO_WORKSPACE_ID)
    if subscription is None:
        session.add(
            DigestSubscription(
                workspace_id=DEMO_WORKSPACE_ID,
                user_id=DEMO_USER_ID,
                cadence="twice_weekly",
                delivery_channel="in_app",
                destination="Atlas Labs team",
                enabled=True,
                next_run_at=DEMO_NOW,
                last_generated_at=None,
                created_at=DEMO_NOW - timedelta(days=20),
                updated_at=DEMO_NOW - timedelta(days=1),
            )
        )
    session.flush()
    if (
        session.scalar(select(DigestRun.id).where(DigestRun.workspace_id == DEMO_WORKSPACE_ID))
        is None
    ):
        DigestService(session).generate(DEMO_WORKSPACE_ID)
    session.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed deterministic EarlySignal demo data")
    parser.add_argument("--reset-only", action="store_true")
    args = parser.parse_args()
    with SessionLocal() as session:
        if args.reset_only:
            _clear_demo(session)
            print("Demo data removed.")
            return
        seed_demo(session)
    print(
        json.dumps(
            {
                "demo": True,
                "workspace_id": DEMO_WORKSPACE_ID,
                "topics": 5,
                "channels": 50,
                "videos": 300,
            }
        )
    )


if __name__ == "__main__":
    main()
