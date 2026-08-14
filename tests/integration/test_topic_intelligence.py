import json
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from apps.api.config import Settings
from apps.api.lifecycle import backfill_lifecycle_history
from apps.api.models import (
    Base,
    ChannelBaseline,
    ChannelProfile,
    CommentTopicRelevance,
    CommentTopicRelevanceEvent,
    DemandCluster,
    DiscoveryQueryRecord,
    LLMIntelligenceRun,
    Signal,
    Topic,
    TopicContentGap,
    TopicContentPattern,
    TopicLifecycleSummary,
    TopicLifecycleTransition,
    TopicPipelineRun,
    TopicSnapshot,
    TopicVideoMembership,
    TopicVideoObservation,
    VideoEmbedding,
    VideoFeature,
    VideoSnapshot,
    Workspace,
    WorkspaceChannel,
    WorkspaceDiscoveryQuery,
    WorkspaceSignalScore,
    YoutubeChannel,
    YoutubeComment,
    YoutubeVideo,
)
from apps.api.services import get_signal_detail, list_signals, resolve_signal_source
from apps.worker.demand_intelligence import DemandIntelligenceService
from apps.worker.topic_intelligence import (
    TopicIntelligenceService,
    _upsert_topic_membership,
)
from apps.worker.video_intelligence import FEATURE_VERSION
from packages.llm_intelligence import LLMProviderResult


class PipelineFakeLLMProvider:
    name = "fake"
    model = "fake-pipeline-model"

    def generate_structured(
        self,
        *,
        task: str,
        developer_prompt: str,
        payload: str,
        response_model: type[BaseModel],
    ) -> LLMProviderResult:
        del developer_prompt
        data = json.loads(payload)
        if task == "topic-synthesis":
            output: dict[str, object] = {
                "canonical_label": "No-code AI agents for recurring company operations",
                "aliases": ["Recurring business automation with no-code agents"],
                "thesis": (
                    "Independent creators are converging on no-code agents that replace "
                    "specific recurring company operations, not generic agent demos."
                ),
                "why_growing": [
                    {
                        "text": "Three independent videos describe the recurring workflow.",
                        "evidence_refs": ["video:video-0", "video:video-1", "video:video-2"],
                    },
                    {
                        "text": "Stored snapshots show channel-relative outlier performance.",
                        "evidence_refs": [
                            "video-snapshot:snapshot-0",
                            "video-snapshot:snapshot-1",
                        ],
                    },
                ],
            }
        elif task == "evidence-insight-synthesis":
            output = {
                "insight": {
                    "topic": "No-code agents are moving into recurring company operations",
                    "statement": (
                        "Independent stored videos show no-code agents being applied to "
                        "specific recurring company operations rather than generic demos."
                    ),
                    "why_non_obvious": (
                        "The shared change is operational specialization, not merely broader "
                        "interest in AI agents."
                    ),
                    "creator_question": (
                        "Which recurring company operations are becoming agent-managed?"
                    ),
                    "insight_kind": "adoption_pattern",
                    "evidence_refs": ["video:video-0", "video:video-1"],
                },
                "no_insight_reason": "",
            }
        elif task in {
            "topic-grounding-audit",
            "content-gap-grounding-audit",
            "evidence-insight-grounding-audit",
        }:
            evidence_ref = data["evidence"][0]["ref"]
            second_evidence_ref = data["evidence"][1]["ref"]
            output = {
                "decision": "accept",
                "summary": "Every expected target is directly supported by stored evidence.",
                "checks": [
                    {
                        "target": target,
                        "verdict": "supported",
                        "rationale": "The stored evidence directly supports this wording.",
                        "evidence_refs": [evidence_ref],
                    }
                    for target in data["expected_targets"]
                ],
            }
            if task == "evidence-insight-grounding-audit":
                output.update(
                    {
                        "non_obviousness": "strong",
                        "decision_value": "changes_creator_decision",
                        "specificity": "specific_mechanism",
                        "generic_restatement": False,
                        "decision_change": (
                            "Challenge the assumption that broad adoption is the main change."
                        ),
                        "evidence_refs": [evidence_ref, second_evidence_ref],
                    }
                )
        else:
            raise AssertionError(f"Unexpected task: {task}")
        return LLMProviderResult(
            output=response_model.model_validate(output),
            response_id=f"fake-{task}",
            model=self.model,
            usage={"input_tokens": 200, "output_tokens": 80, "total_tokens": 280},
            latency_ms=15,
        )


class RejectingAuditPipelineProvider(PipelineFakeLLMProvider):
    model = "fake-rejecting-auditor-model"

    def generate_structured(
        self,
        *,
        task: str,
        developer_prompt: str,
        payload: str,
        response_model: type[BaseModel],
    ) -> LLMProviderResult:
        if task not in {
            "topic-grounding-audit",
            "content-gap-grounding-audit",
            "evidence-insight-grounding-audit",
        }:
            return super().generate_structured(
                task=task,
                developer_prompt=developer_prompt,
                payload=payload,
                response_model=response_model,
            )
        data = json.loads(payload)
        evidence_ref = data["evidence"][0]["ref"]
        checks = [
            {
                "target": target,
                "verdict": "unsupported" if index == 0 else "supported",
                "rationale": (
                    "The wording exceeds the stored evidence."
                    if index == 0
                    else "The stored evidence supports this target."
                ),
                "evidence_refs": [evidence_ref],
            }
            for index, target in enumerate(data["expected_targets"])
        ]
        output = {
            "decision": "reject",
            "summary": "At least one material target is not grounded.",
            "checks": checks,
        }
        if task == "evidence-insight-grounding-audit":
            output.update(
                {
                    "non_obviousness": "obvious",
                    "decision_value": "none",
                    "specificity": "broad_claim",
                    "generic_restatement": True,
                    "decision_change": "The candidate would not change a creator decision.",
                    "evidence_refs": [
                        data["evidence"][0]["ref"],
                        data["evidence"][1]["ref"],
                    ],
                }
            )
        return LLMProviderResult(
            output=response_model.model_validate(output),
            response_id=f"fake-{task}",
            model=self.model,
            usage={"input_tokens": 200, "output_tokens": 80, "total_tokens": 280},
            latency_ms=15,
        )


def test_content_patterns_are_idempotent_across_workspace_scoring_before_flush() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    observed_at = datetime(2026, 7, 30, 19, tzinfo=UTC)
    content_gap_map = {
        "patterns": [
            {
                "video_id": "shared-video",
                "pattern_key": "implementation_walkthrough",
                "evidence_refs": ["video:shared-video"],
            }
        ],
        "opportunities": [
            {
                "gap_key": "missing_tradeoff",
                "rank": 1,
                "occupied_pattern": {"pattern_key": "implementation_walkthrough"},
                "open_gap": {"question": "What breaks in production?"},
                "score_components": {"novelty": 0.8},
                "evidence": ["video:shared-video"],
            }
        ],
    }
    with Session(engine, expire_on_commit=False) as session:
        service = TopicIntelligenceService(session, Settings())

        service._persist_content_gap_map(
            workspace_id="workspace-a",
            topic_id="shared-topic",
            content_gap_map=content_gap_map,
            observed_at=observed_at,
        )
        service._persist_content_gap_map(
            workspace_id="workspace-b",
            topic_id="shared-topic",
            content_gap_map=content_gap_map,
            observed_at=observed_at,
        )
        session.commit()

        assert session.scalar(select(func.count(TopicContentPattern.id))) == 1
        assert session.scalar(select(func.count(TopicContentGap.id))) == 2


def test_lifecycle_backfill_is_point_in_time_and_idempotent() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    formed_at = datetime(2026, 7, 20, 12, tzinfo=UTC)
    with Session(engine, expire_on_commit=False) as session:
        session.add(
            Topic(
                id="topic-history",
                canonical_label="Local agent workflow",
                aliases_json=[],
                entities_json=["local agents"],
                centroid_embedding=[],
                embedding_model="test",
                embedding_version="test",
                first_observed_at=formed_at - timedelta(days=1),
                first_confirmed_at=formed_at,
                lifecycle_stage="Breakout",
                status="active",
                source_kind="live",
                merged_into_topic_id=None,
                clustering_version="test",
            )
        )
        snapshot_inputs = (
            ("history-seed", 1, 1, 1, 100.0, 10.0, 31.0),
            ("history-emerging", 2, 3, 3, 500.0, 20.0, 58.0),
            ("history-breakout", 3, 6, 6, 4_000.0, 30.0, 74.0),
        )
        for index, (
            snapshot_id,
            video_24h,
            video_72h,
            channels,
            velocity,
            saturation,
            score,
        ) in enumerate(snapshot_inputs):
            session.add(
                TopicSnapshot(
                    id=snapshot_id,
                    topic_id="topic-history",
                    observed_at=formed_at + timedelta(days=index * 2),
                    video_count_24h=video_24h,
                    video_count_72h=video_72h,
                    distinct_channels_72h=channels,
                    aggregate_view_velocity=velocity,
                    median_outlier_ratio=1.5,
                    large_channel_count=0,
                    demand_score=0,
                    saturation_score=saturation,
                    fragility_score=20,
                    component_json={
                        "previous_video_count_24h": max(0, video_24h - 1),
                        "distinct_channels": channels,
                        "top_outlier_ratio": 2.2,
                        "top_velocity_share": 0.4,
                        "baseline_coverage": 0.8,
                        "specificity_score": 80,
                        "score": score,
                    },
                )
            )
        session.commit()

        first = backfill_lifecycle_history(session, source_kind="live")
        session.commit()
        second = backfill_lifecycle_history(session, source_kind="live")
        session.commit()

        assert first.topics_processed == 1
        assert first.transitions_created == 3
        assert first.summaries_created == 1
        assert second.transitions_created == 0
        assert second.summaries_created == 0
        transitions = list(
            session.scalars(
                select(TopicLifecycleTransition).order_by(TopicLifecycleTransition.transitioned_at)
            )
        )
        assert [(row.from_stage, row.to_stage) for row in transitions] == [
            (None, "Seed"),
            ("Seed", "Emerging"),
            ("Emerging", "Breakout"),
        ]
        summary = session.get(TopicLifecycleSummary, "topic-history")
        assert summary is not None
        assert summary.first_signal_visible_at is not None
        assert summary.first_breakout_at is not None
        assert (
            summary.first_breakout_at.replace(tzinfo=UTC)
            - summary.first_signal_visible_at.replace(tzinfo=UTC)
        ) == timedelta(days=2)

        first_snapshot = session.get(TopicSnapshot, "history-seed")
        assert first_snapshot is not None
        first_snapshot.saturation_score = 90
        session.commit()
        replay = backfill_lifecycle_history(session, source_kind="live")
        session.commit()
        assert replay.transitions_created == 0
        assert session.get(TopicLifecycleTransition, transitions[0].id).to_stage == "Seed"


def test_real_videos_become_stable_evidence_backed_signals(tmp_path) -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    now = datetime.now(tz=UTC)
    with Session(engine, expire_on_commit=False) as session:
        session.add(
            Workspace(
                id="workspace-1",
                name="Creator workspace",
                slug="creator",
                plan="private_beta",
                timezone="UTC",
                created_at=now,
            )
        )
        channels: list[YoutubeChannel] = []
        for index in range(4):
            channel = YoutubeChannel(
                id=f"channel-{index}",
                youtube_channel_id=f"UC_REAL_{index:02d}",
                canonical_url=f"https://youtube.com/channel/UC_REAL_{index:02d}",
                title=f"Channel {index}",
                description="",
                country="US",
                default_language="en",
                subscriber_count=25_000 * (index + 1),
                video_count=100,
                view_count=1_000_000,
                published_at=now - timedelta(days=1000),
                last_observed_at=now,
                created_at=now,
                updated_at=now,
            )
            channels.append(channel)
            session.add(channel)
            session.add(
                ChannelBaseline(
                    id=f"baseline-{index}",
                    channel_id=channel.id,
                    window="rolling_180d",
                    metric_name="median_views_age_curve_coefficient",
                    metric_value=250,
                    sample_size=12,
                    calculated_at=now,
                    version="channel-baseline-v1",
                )
            )
        session.add(
            WorkspaceChannel(
                workspace_id="workspace-1",
                channel_id=channels[0].id,
                relationship="owned",
                priority=0,
                active=True,
                last_ingested_at=None,
                next_ingestion_at=None,
            )
        )
        titles = (
            "Generate Unlimited AI Videos on Your PC",
            "Best Local AI Video Generator for Beginners",
            "Free Text-to-Video Models Compared",
        )
        for index, title in enumerate(titles):
            video = YoutubeVideo(
                id=f"video-{index}",
                youtube_video_id=f"real-video-{index}",
                channel_id=channels[index + 1].id,
                canonical_url=f"https://youtube.com/watch?v=real-video-{index}",
                title=title,
                description="A practical AI video generation workflow.",
                published_at=now - timedelta(hours=4 + index),
                duration_seconds=600,
                default_language="en",
                category_id="28",
                is_short=False,
                is_live=False,
                thumbnail_url="https://example.com/thumb.jpg",
                first_discovered_at=now - timedelta(hours=2),
                discovery_lag_seconds=7200,
                last_observed_at=now,
                created_at=now,
                updated_at=now,
            )
            session.add(video)
            session.add(
                VideoSnapshot(
                    id=f"snapshot-{index}",
                    video_id=video.id,
                    observed_at=now,
                    video_age_seconds=(4 + index) * 3600,
                    view_count=10_000 * (index + 1),
                    like_count=500,
                    comment_count=50,
                    views_per_hour=1500 + index * 300,
                    likes_per_1000_views=50,
                    comments_per_1000_views=5,
                    snapshot_quality="direct",
                    is_estimated=False,
                    provider_fetch_id=None,
                )
            )
            session.add(
                VideoFeature(
                    video_id=video.id,
                    feature_version=FEATURE_VERSION,
                    language_probability=1,
                    vertical_relevance=0.95,
                    outlier_ratio=1.5 + index * 0.2,
                    view_velocity=1500 + index * 300,
                    velocity_acceleration=20,
                    engagement_rate=55,
                    novelty_score=0,
                    spam_probability=0,
                    calculated_at=now,
                )
            )
        session.commit()

        service = TopicIntelligenceService(
            session,
            Settings(
                raw_payload_directory=str(tmp_path),
                feature_earlyness_timeline=True,
            ),
        )
        first = service.run(force=True)
        second = service.run(force=True)

        assert first.topics == 1
        assert first.signals == 1
        assert first.assigned_videos == 3
        assert second.topics == 1
        assert session.scalar(select(func.count(Topic.id))) == 1
        assert session.scalar(select(func.count(Signal.id))) == 1
        assert session.scalar(select(func.count(VideoEmbedding.video_id))) == 3
        assert session.scalar(select(func.count(TopicSnapshot.id))) == 2
        assert session.scalar(select(func.count(TopicLifecycleTransition.id))) == 1
        assert session.scalar(select(func.count(TopicLifecycleSummary.topic_id))) == 1
        assert session.scalar(select(func.count(WorkspaceSignalScore.signal_id))) == 1
        membership = session.scalar(select(TopicVideoMembership))
        assert membership is not None
        observation = session.scalar(select(TopicVideoObservation))
        assert observation is not None
        assert observation.first_observation_quality == "direct"
        first_observed_at = observation.first_observed_at
        initial_observation_count = observation.observation_count
        membership_count = session.scalar(select(func.count(TopicVideoMembership.video_id)))
        _upsert_topic_membership(
            session,
            topic_id=membership.topic_id,
            video_id=membership.video_id,
            membership_score=0.87,
            assignment_method="regression-test",
            evidence_role="driver",
            assigned_at=now,
        )
        _upsert_topic_membership(
            session,
            topic_id=membership.topic_id,
            video_id=membership.video_id,
            membership_score=0.91,
            assignment_method="regression-test",
            evidence_role="driver",
            assigned_at=now,
        )
        session.commit()
        assert session.scalar(select(func.count(TopicVideoMembership.video_id))) == membership_count
        session.refresh(membership)
        assert membership.membership_score == 0.91
        session.refresh(observation)
        assert observation.first_observed_at == first_observed_at
        assert observation.last_observed_at.replace(tzinfo=UTC) == now
        assert observation.observation_count == initial_observation_count + 2
        workspace_score = session.scalar(select(WorkspaceSignalScore))
        profile = session.scalar(select(ChannelProfile))
        assert workspace_score is not None
        assert profile is not None
        assert workspace_score.fit_version == "channel-fit-v1"
        assert len(workspace_score.recommended_angle_json) == 3
        assert workspace_score.recommended_angle_json[0]["opportunity_id"]
        assert workspace_score.recommended_angle_json[0]["best_publish_window"]["label"]
        assert {
            "topical_relevance",
            "audience_overlap",
            "format_compatibility",
            "authority_or_credibility",
            "production_feasibility",
            "historical_performance_similarity",
            "timing_feasibility",
            "cannibalization_penalty",
            "brand_risk_penalty",
        }.issubset(workspace_score.fit_component_json)

        mode, modes = resolve_signal_source(session, "workspace-1", "auto")
        feed = list_signals(
            session,
            "workspace-1",
            source_kind=mode,
            include_earlyness=True,
        )
        assert mode == "live"
        assert modes == ["live"]
        assert len(feed) == 1
        assert feed[0].strongest_demand.available is False
        assert feed[0].data_mode == "live"
        assert len(feed[0].evidence_preview) == 3
        assert all(
            item.canonical_url.startswith("https://youtube.com/")
            for item in feed[0].evidence_preview
        )
        assert feed[0].earlyness is not None
        assert feed[0].earlyness.current_stage == "Emerging"
        assert feed[0].earlyness.claim_kind == "pending"
        summary = session.scalar(select(TopicLifecycleSummary))
        assert summary is not None
        first_visible_at = summary.first_signal_visible_at
        assert first_visible_at is not None

        for video_index in range(3):
            for comment_index in range(2):
                comment_id = f"comment-{video_index}-{comment_index}"
                session.add(
                    YoutubeComment(
                        id=comment_id,
                        provider_comment_id=comment_id,
                        video_id=f"video-{video_index}",
                        parent_comment_id=None,
                        text=(
                            "Please make a step by step tutorial for the local setup?"
                            if comment_index == 0
                            else "Can you explain how beginners reproduce this workflow on a GPU?"
                        ),
                        published_at=now - timedelta(hours=video_index + comment_index),
                        updated_at=None,
                        like_count=20 - comment_index,
                        reply_count=2,
                        is_reply=False,
                        language="en",
                        author_hash=f"author-{video_index}-{comment_index}",
                        fetched_order="relevance",
                        normalized_hash=f"hash-{video_index}-{comment_index}",
                        provider_fetch_id=None,
                        created_at=now,
                    )
                )
        session.commit()

        demand = DemandIntelligenceService(
            session,
            Settings(
                raw_payload_directory=str(tmp_path),
                feature_comment_topic_relevance=True,
            ),
        )
        assert demand.classify_comments() == 6
        relevance = demand.classify_comment_relevance()
        assert relevance.evaluated == 6
        assert relevance.accepted == 3
        assert relevance.rejected == 3
        assert relevance.changed == 6
        assert demand.cluster_demand(observed_at=now) == 1
        service.run(force=True)

        cluster = session.scalar(select(DemandCluster))
        signal = session.scalar(select(Signal))
        assert cluster is not None
        assert cluster.distinct_video_count == 3
        assert cluster.distinct_channel_count == 3
        assert cluster.distinct_commenter_count == 3
        assert cluster.comment_count == 3
        assert cluster.visibility_status == "user_visible"
        assert cluster.evidence_strength in {"Moderate", "Strong"}
        assert cluster.median_relevance_score is not None
        assert cluster.median_relevance_score >= 0.70
        assert cluster.relevance_model_version == "comment-topic-relevance-v1"
        assert signal is not None
        assert signal.component_json["audience_demand"] > 0
        assert session.scalar(select(func.count(TopicLifecycleTransition.id))) == 1
        session.refresh(summary)
        assert summary.first_signal_visible_at == first_visible_at

        feed_with_demand = list_signals(session, "workspace-1", source_kind="live")
        assert feed_with_demand[0].strongest_demand.available is True
        assert feed_with_demand[0].strongest_demand.distinct_videos == 3
        assert feed_with_demand[0].strongest_demand.comment_count == 3
        assert session.scalar(select(func.count(CommentTopicRelevance.id))) == 6
        assert session.scalar(select(func.count(CommentTopicRelevanceEvent.id))) == 6

        replay = demand.replay_relevance()
        assert replay.evaluated == 6
        assert replay.changed == 0
        assert session.scalar(select(func.count(CommentTopicRelevanceEvent.id))) == 6

        cycled_video = session.get(YoutubeVideo, "video-0")
        assert cycled_video is not None
        original_title = cycled_video.title
        cycled_video.title = f"{original_title} updated"
        session.commit()

        changed_relevance = demand.classify_comment_relevance()
        assert changed_relevance.changed == 2
        assert session.scalar(select(func.count(CommentTopicRelevanceEvent.id))) == 8

        cycled_video.title = original_title
        session.commit()

        restored_relevance = demand.classify_comment_relevance()
        assert restored_relevance.changed == 2
        assert session.scalar(select(func.count(CommentTopicRelevanceEvent.id))) == 10

        v6_titles = (
            "No-Code AI Agents for Recurring Business Tasks",
            "Automate Recurring Company Work With AI Agents — No Code",
            "Build a No-Code AI Agent for Repetitive Company Work",
        )
        for index, title in enumerate(v6_titles):
            video = session.get(YoutubeVideo, f"video-{index}")
            assert video is not None
            video.title = title
            video.description = (
                "Business teams replace a recurring manual operation with an "
                "evidence-backed AI agent workflow without coding."
            )
        session.commit()

        v6_service = TopicIntelligenceService(
            session,
            Settings(
                raw_payload_directory=str(tmp_path),
                feature_earlyness_timeline=True,
                feature_microtopic_content_gap=True,
                feature_channel_profile_feasibility_v2=True,
            ),
        )
        v6_result = v6_service.run(force=True)

        assert v6_result.topics == 1
        assert v6_result.signals == 1
        v6_topic = session.scalar(
            select(Topic).where(
                Topic.clustering_version == "microtopic-clustering-v6-subject-event",
                Topic.status == "active",
            )
        )
        assert v6_topic is not None
        assert v6_topic.identity_json["audience"] == "business teams"
        assert v6_topic.identity_json["user_problem"] == "workplace adoption"
        assert v6_topic.identity_json["lineage"]["semantic_fingerprint"]
        assert v6_topic.specificity_score >= 70
        assert v6_topic.thesis_support_ratio >= 0.8
        v6_snapshot = session.scalar(
            select(TopicSnapshot)
            .where(TopicSnapshot.topic_id == v6_topic.id)
            .order_by(TopicSnapshot.observed_at.desc())
        )
        assert v6_snapshot is not None
        assert v6_snapshot.component_json["topic_identity"] == v6_topic.identity_json["lineage"]
        assert (
            session.scalar(
                select(func.count(TopicContentPattern.id)).where(
                    TopicContentPattern.topic_id == v6_topic.id
                )
            )
            == 3
        )
        assert (
            session.scalar(
                select(func.count(TopicContentGap.id)).where(
                    TopicContentGap.workspace_id == "workspace-1",
                    TopicContentGap.topic_id == v6_topic.id,
                    TopicContentGap.status == "active",
                )
            )
            == 3
        )

        v6_signal = session.scalar(
            select(Signal).where(
                Signal.topic_id == v6_topic.id,
                Signal.status == "active",
            )
        )
        assert v6_signal is not None
        v6_score = session.get(WorkspaceSignalScore, ("workspace-1", v6_signal.id))
        assert v6_score is not None
        assert len(v6_score.recommended_angle_json) == 3
        primary = v6_score.recommended_angle_json[0]
        assert primary["occupied_pattern"]
        assert primary["open_gap"]
        assert primary["differentiation"]
        assert primary["evidence"]
        assert primary["why_primary"]

        detail = get_signal_detail(
            session,
            "workspace-1",
            v6_signal.id,
            include_content_gap=True,
            include_decision=True,
            use_feasibility_v2=True,
        )
        assert detail.topic["clustering_version"] == ("microtopic-clustering-v6-subject-event")
        assert detail.content_gap_map is not None
        assert detail.content_gap_map["pattern_version"] == "topic-content-pattern-v1"
        assert detail.content_gap_map["gap_version"] == "content-gap-v4"
        assert detail.content_gap_map["ranking_version"] == "opportunity-ranking-v5"
        assert len(detail.content_gap_map["gaps"]) == 3
        assert "release_ready" in detail.content_angles[0]
        assert "insight_status" in detail.content_angles[0]
        assert "insight_statement" in detail.content_angles[0]
        assert detail.content_angles[0]["recommended_publish_by"]
        assert detail.content_angles[0]["feasibility"] in {
            "High",
            "Medium",
            "Infeasible",
        }
        assert detail.content_angles[0]["decay_version"] == (
            "creator-specific-opportunity-decay-v1"
        )
        assert detail.decision_card is not None
        if detail.content_angles[0]["feasible_for_act"] is False:
            assert detail.decision_card.decision == "Skip"

        deterministic_score = v6_signal.score
        deterministic_label = v6_topic.canonical_label
        llm_service = TopicIntelligenceService(
            session,
            Settings(
                raw_payload_directory=str(tmp_path),
                feature_earlyness_timeline=True,
                feature_microtopic_content_gap=True,
                feature_channel_profile_feasibility_v2=True,
                feature_llm_intelligence=True,
            ),
            llm_provider=PipelineFakeLLMProvider(),
        )
        llm_result = llm_service.run(force=True)

        assert llm_result.topics == 1
        llm_topic = session.scalar(
            select(Topic).where(
                Topic.clustering_version == "microtopic-clustering-v6-subject-event",
                Topic.status == "active",
            )
        )
        assert llm_topic is not None
        assert llm_topic.canonical_label == ("No-code AI agents for recurring company operations")
        llm_signal = session.scalar(
            select(Signal).where(
                Signal.topic_id == llm_topic.id,
                Signal.status == "active",
            )
        )
        assert llm_signal is not None
        assert llm_signal.score == deterministic_score
        assert llm_signal.synthesis_json["method"] == "llm"
        assert len(llm_signal.synthesis_json["why_growing"]) == 2
        llm_score = session.get(
            WorkspaceSignalScore,
            ("workspace-1", llm_signal.id),
        )
        assert llm_score is not None
        assert llm_score.recommended_angle_json[0]["title"] != (
            "No-code agents are moving into recurring company operations"
        )
        llm_detail = get_signal_detail(
            session,
            "workspace-1",
            llm_signal.id,
            include_content_gap=True,
        )
        assert len(llm_detail.why_emerging_evidence) == 2
        assert llm_detail.why_emerging_evidence[0].evidence_refs
        assert llm_detail.intelligence_provenance["model"] == "fake-pipeline-model"
        assert session.scalar(select(func.count(LLMIntelligenceRun.id))) == 2
        pipeline_run = session.get(TopicPipelineRun, llm_result.run_id)
        assert pipeline_run is not None
        assert pipeline_run.llm_policy_version == "evidence-decision-graph-v1"
        assert pipeline_run.llm_trace_json["provider_calls"] == 2
        assert pipeline_run.llm_trace_json["decisions"]["accept"] == 1

        legacy_gap = TopicContentGap(
            id="legacy-workspace-gap",
            workspace_id="workspace-1",
            topic_id=llm_topic.id,
            gap_key="legacy-gap",
            rank=1,
            status="active",
            occupied_pattern_json={},
            open_gap_json={},
            score_components_json={},
            evidence_json=[],
            model_version="content-gap-v1",
            ranking_version="opportunity-ranking-v1",
            calculated_at=now,
        )
        session.add(legacy_gap)
        session.commit()
        enrichment = llm_service.enrich_workspace("workspace-1")
        assert enrichment.workspace_id == "workspace-1"
        assert enrichment.signals_processed == 1
        assert enrichment.evidence_insights_released == 1
        assert legacy_gap.status == "superseded"
        assert enrichment.llm_trace["workflow_run_id"].startswith(
            "workspace-enrichment:workspace-1:"
        )
        assert enrichment.llm_trace["decisions"]["accept"] == 1
        session.refresh(llm_score)
        assert llm_score.recommended_angle_json[0]["title"] == (
            "No-code agents are moving into recurring company operations"
        )
        assert llm_score.recommended_angle_json[0]["insight_type"] == ("audited_adoption_pattern")
        assert llm_score.recommended_angle_json[0]["llm"]["model"] == ("fake-pipeline-model")

        rejected_service = TopicIntelligenceService(
            session,
            Settings(
                raw_payload_directory=str(tmp_path),
                feature_earlyness_timeline=True,
                feature_microtopic_content_gap=True,
                feature_channel_profile_feasibility_v2=True,
                feature_llm_intelligence=True,
            ),
            llm_provider=RejectingAuditPipelineProvider(),
        )
        rejected_result = rejected_service.run(force=True)
        rejected_topic = session.scalar(
            select(Topic).where(
                Topic.clustering_version == "microtopic-clustering-v6-subject-event",
                Topic.status == "active",
            )
        )
        assert rejected_topic is not None
        assert rejected_topic.canonical_label == deterministic_label
        rejected_signal = session.scalar(
            select(Signal).where(
                Signal.topic_id == rejected_topic.id,
                Signal.status == "active",
            )
        )
        assert rejected_signal is not None
        assert rejected_signal.score == deterministic_score
        assert rejected_signal.synthesis_json["method"] == "deterministic"
        rejected_score = session.get(
            WorkspaceSignalScore,
            ("workspace-1", rejected_signal.id),
        )
        assert rejected_score is not None
        assert rejected_score.recommended_angle_json[0]["title"] != (
            "No-code agents are moving into recurring company operations"
        )
        rejected_run = session.get(TopicPipelineRun, rejected_result.run_id)
        assert rejected_run is not None
        assert rejected_run.llm_trace_json["decisions"]["fallback"] == 1

        session.add(
            DiscoveryQueryRecord(
                id="personal-query-1",
                query="developer interview job market 2026",
                category="AI / tech",
                priority=1,
                country="US",
                language="en",
                active=True,
                source="channel_profile",
                minimum_interval_seconds=14_400,
                expires_at=None,
                last_run_at=None,
                next_run_at=now,
            )
        )
        session.add(
            WorkspaceDiscoveryQuery(
                workspace_id="workspace-1",
                query_id="personal-query-1",
                source_type="channel_profile",
                rationale="Ground the feed in this workspace's topic plan.",
                evidence_refs_json=["channel:channel-owned"],
                active=True,
            )
        )
        session.commit()

        assert list_signals(session, "workspace-1", source_kind="live") == []
