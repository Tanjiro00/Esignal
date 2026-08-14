from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from statistics import median
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from apps.api.models import (
    ChannelProfile,
    Signal,
    TopicSnapshot,
    VideoFeature,
    VideoTranscript,
    Workspace,
    YoutubeOAuthConnection,
    YoutubeOwnedAnalytics,
    YoutubeVideo,
)
from apps.worker.video_intelligence import FEATURE_VERSION
from packages.channel_fit import (
    FIT_VERSION,
    ChannelFitComponents,
    calculate_channel_fit,
    token_overlap_score,
)
from packages.channel_fit.scoring import bounded, tokens
from packages.clustering import normalize_entities
from packages.content_gap import build_content_gap_map, extract_content_pattern
from packages.production_feasibility import (
    FeasibilityAssessment,
    assess_production_feasibility,
)


@dataclass(frozen=True)
class ChannelFitResult:
    score: float
    components: dict[str, object]
    opportunities: list[dict[str, object]]
    content_gap_map: dict[str, object] | None


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _duration_score(value: float, low: int, high: int) -> float:
    if value <= 0:
        return 50
    if low <= value <= high:
        return 95
    distance = low - value if value < low else value - high
    reference = max(high - low, 300)
    return bounded(90 - distance / reference * 55)


def _window_label(start: datetime, end: datetime, observed_at: datetime) -> str:
    start_days = max(0, round((_aware(start) - observed_at).total_seconds() / 86_400))
    end_days = max(start_days, round((_aware(end) - observed_at).total_seconds() / 86_400))
    return f"{start_days}–{end_days} days"


class ChannelFitService:
    def __init__(
        self,
        session: Session,
        *,
        content_gap_enabled: bool = False,
        feasibility_v2_enabled: bool = False,
        verified_analytics_enabled: bool = False,
    ) -> None:
        self._session = session
        self._content_gap_enabled = content_gap_enabled
        self._feasibility_v2_enabled = feasibility_v2_enabled
        self._verified_analytics_enabled = verified_analytics_enabled

    def score(
        self,
        *,
        profile: ChannelProfile,
        signal: Signal,
        topic_values: list[str],
        evidence_videos: list[YoutubeVideo],
        vertical_relevance: list[float],
        provisional_angles: list[dict[str, object]],
        observed_at: datetime,
        demand_supported: bool = False,
    ) -> ChannelFitResult:
        history = list(
            self._session.scalars(
                select(YoutubeVideo)
                .where(YoutubeVideo.channel_id == profile.channel_id)
                .order_by(desc(YoutubeVideo.published_at))
                .limit(40)
            )
        )
        profile_values = [
            profile.audience_description,
            *profile.core_topics_json,
            *profile.adjacent_topics_json,
            *profile.topic_keywords_json,
            *profile.creator_expertise_json,
            *profile.strategic_goals_json,
        ]
        history_titles = [item.title for item in history]
        semantic_fit = token_overlap_score(
            topic_values,
            [*profile_values, *history_titles],
            floor=25,
        )
        observed_vertical = (
            sum(vertical_relevance) / len(vertical_relevance) * 100 if vertical_relevance else 50
        )
        topical_relevance = semantic_fit * 0.7 + observed_vertical * 0.3

        language_match = (
            sum(
                item.default_language.lower().startswith(profile.language.lower()[:2])
                for item in evidence_videos
            )
            / len(evidence_videos)
            * 100
            if evidence_videos
            else 50
        )
        audience_semantic = token_overlap_score(
            topic_values,
            [profile.audience_description, *profile.strategic_goals_json],
            floor=35,
        )
        audience_overlap = audience_semantic * 0.7 + language_match * 0.3

        evidence_durations = [
            item.duration_seconds for item in evidence_videos if item.duration_seconds > 0
        ]
        evidence_duration = median(evidence_durations) if evidence_durations else 0
        format_compatibility = _duration_score(
            evidence_duration,
            profile.normal_duration_min_seconds,
            profile.normal_duration_max_seconds,
        )
        authority_overlap = token_overlap_score(
            topic_values,
            profile.creator_expertise_json,
            floor=30,
        )
        matching_history = [item for item in history if tokens(item.title) & tokens(topic_values)]
        authority = bounded(authority_overlap + min(20, len(matching_history) * 4))

        window_days = max(
            0.5,
            (_aware(signal.opportunity_end) - observed_at).total_seconds() / 86_400,
        )
        production_feasibility = bounded(
            100
            if profile.production_days_max <= window_days
            else window_days / max(profile.production_days_max, 1) * 100
        )
        timing_feasibility = bounded(
            100
            if profile.production_days_min <= window_days
            else window_days / max(profile.production_days_min, 1) * 100
        )

        matching_ids = [item.id for item in matching_history]
        matching_features = (
            list(
                self._session.scalars(
                    select(VideoFeature).where(
                        VideoFeature.video_id.in_(matching_ids),
                        VideoFeature.feature_version == FEATURE_VERSION,
                    )
                )
            )
            if matching_ids
            else []
        )
        if matching_features:
            historical_performance = bounded(
                median(item.outlier_ratio for item in matching_features) * 50
            )
        else:
            historical_performance = 45 if history else 35
        fit_verification = "estimated"
        verified_analytics_sample_size = 0
        if self._verified_analytics_enabled:
            connection = self._session.get(
                YoutubeOAuthConnection,
                profile.workspace_id,
            )
            if connection is not None and connection.status == "active":
                analytics_rows = list(
                    self._session.scalars(
                        select(YoutubeOwnedAnalytics)
                        .where(
                            YoutubeOwnedAnalytics.workspace_id == profile.workspace_id,
                            YoutubeOwnedAnalytics.video_id.in_([item.id for item in history]),
                        )
                        .order_by(desc(YoutubeOwnedAnalytics.period_end))
                    )
                )
                latest_by_video: dict[str, YoutubeOwnedAnalytics] = {}
                for analytics in analytics_rows:
                    if analytics.video_id is not None:
                        latest_by_video.setdefault(analytics.video_id, analytics)
                all_views = [item.views for item in latest_by_video.values() if item.views > 0]
                matching_views = [
                    latest_by_video[video_id].views
                    for video_id in matching_ids
                    if video_id in latest_by_video and latest_by_video[video_id].views > 0
                ]
                if all_views:
                    fit_verification = "verified"
                    verified_analytics_sample_size = len(all_views)
                if all_views and matching_views:
                    historical_performance = bounded(
                        median(matching_views) / max(median(all_views), 1) * 50
                    )

        recent_cutoff = observed_at - timedelta(days=45)
        cannibalization = max(
            (
                token_overlap_score(topic_values, [item.title], floor=0)
                for item in matching_history
                if _aware(item.published_at) >= recent_cutoff
            ),
            default=0,
        )
        brand_risk = token_overlap_score(
            topic_values,
            profile.exclusions_json,
            floor=0,
        )
        raw_components = ChannelFitComponents(
            topical_relevance=topical_relevance,
            audience_overlap=audience_overlap,
            format_compatibility=format_compatibility,
            authority_or_credibility=authority,
            production_feasibility=production_feasibility,
            historical_performance_similarity=historical_performance,
            timing_feasibility=timing_feasibility,
            cannibalization_penalty=cannibalization,
            brand_risk_penalty=brand_risk,
        ).normalized()
        score = calculate_channel_fit(raw_components)
        component_values = asdict(raw_components)
        strongest = sorted(
            (
                (key, float(value))
                for key, value in component_values.items()
                if not key.endswith("_penalty")
            ),
            key=lambda item: item[1],
            reverse=True,
        )[:3]
        explanation = (
            f"Fit {score}/100 for this owned channel. Strongest signals: "
            + ", ".join(f"{key.replace('_', ' ')} {value:.0f}" for key, value in strongest)
            + f". Production range {profile.production_days_min}–"
            f"{profile.production_days_max} days versus "
            f"{window_days:.0f} days remaining."
        )
        components: dict[str, object] = {
            **component_values,
            "fit_version": FIT_VERSION,
            "profile_source": profile.profile_source,
            "history_sample_size": len(history),
            "matching_history_count": len(matching_history),
            "evidence_duration_median_seconds": round(evidence_duration),
            "production_window_days": round(window_days, 1),
            "fit_verification": fit_verification,
            "verified_analytics_sample_size": verified_analytics_sample_size,
            "explanation": explanation,
        }
        reason_codes = [f"strong_{key}" for key, value in strongest if value >= 70]
        if raw_components.brand_risk_penalty >= 40:
            reason_codes.append("brand_risk_penalty")
        if raw_components.cannibalization_penalty >= 50:
            reason_codes.append("recent_topic_cannibalization")
        components["reason_codes"] = reason_codes or ["limited_channel_history"]
        content_gap_map: dict[str, object] | None = None
        opportunity_angles = provisional_angles
        if self._content_gap_enabled:
            evidence_features = {
                feature.video_id: feature
                for feature in self._session.scalars(
                    select(VideoFeature).where(
                        VideoFeature.video_id.in_([video.id for video in evidence_videos]),
                        VideoFeature.feature_version == FEATURE_VERSION,
                    )
                )
            }
            transcript_by_video = {
                transcript.video_id: transcript
                for transcript in self._session.scalars(
                    select(VideoTranscript).where(
                        VideoTranscript.video_id.in_([video.id for video in evidence_videos])
                    )
                )
            }
            patterns = []
            for video in evidence_videos:
                transcript = transcript_by_video.get(video.id)
                semantic_description = " ".join(
                    part
                    for part in (
                        video.description,
                        str(transcript.summary_json.get("text", ""))
                        if transcript is not None
                        else "",
                    )
                    if part
                )
                entities = tuple(
                    dict.fromkeys(
                        (
                            *normalize_entities(video.title, semantic_description),
                            *topic_values,
                        )
                    )
                )
                patterns.append(
                    extract_content_pattern(
                        video_id=video.id,
                        title=video.title,
                        description=semantic_description,
                        entities=entities,
                        transcript_format=(
                            transcript.content_format if transcript is not None else None
                        ),
                        narrative_angle=(
                            transcript.narrative_angle if transcript is not None else None
                        ),
                        channel_id=video.channel_id,
                        outlier_ratio=(
                            evidence_features[video.id].outlier_ratio
                            if video.id in evidence_features
                            else 1.0
                        ),
                    )
                )
            demand_question = str(
                provisional_angles[0].get("unanswered_question", "") if provisional_angles else ""
            )
            evidence_refs: list[str] = []
            for angle in provisional_angles:
                raw_evidence = angle.get("evidence", [])
                if isinstance(raw_evidence, list):
                    evidence_refs.extend(
                        str(reference) for reference in raw_evidence if isinstance(reference, str)
                    )
            content_gap_map = build_content_gap_map(
                topic_label=str(topic_values[0] if topic_values else "Emerging topic"),
                patterns=patterns,
                profile_audience=profile.audience_description,
                preferred_formats=profile.preferred_formats_json,
                demand_question=demand_question,
                evidence_refs=evidence_refs,
                channel_fit=score,
                production_feasibility=raw_components.production_feasibility,
                timing=raw_components.timing_feasibility,
                brand_risk=raw_components.brand_risk_penalty,
                demand_supported=demand_supported,
            )
            raw_opportunities = content_gap_map.get("opportunities", [])
            opportunity_angles = (
                [
                    dict(opportunity)
                    for opportunity in raw_opportunities
                    if isinstance(opportunity, dict)
                ]
                if isinstance(raw_opportunities, list)
                else []
            )

        feasibility: FeasibilityAssessment | None = None
        if self._feasibility_v2_enabled:
            workspace = self._session.get(Workspace, profile.workspace_id)
            latest_topic_snapshot = self._session.scalar(
                select(TopicSnapshot)
                .where(TopicSnapshot.topic_id == signal.topic_id)
                .order_by(desc(TopicSnapshot.observed_at))
                .limit(1)
            )
            requires_product_access = any(
                str(angle.get("format", "")).lower()
                in {"hands-on test", "case study", "challenge / build diary"}
                for angle in opportunity_angles
            )
            feasibility = assess_production_feasibility(
                observed_at=observed_at,
                opportunity_end=signal.opportunity_end,
                workspace_timezone=workspace.timezone if workspace is not None else "UTC",
                lifecycle_stage=signal.lifecycle_stage,
                adoption_rate=float(signal.component_json.get("momentum", 0)),
                large_channel_entry=(
                    latest_topic_snapshot is not None
                    and latest_topic_snapshot.large_channel_count > 0
                ),
                production_days_min=profile.production_days_min,
                production_days_max=profile.production_days_max,
                team_size=profile.team_size,
                research_capacity_hours=profile.research_capacity_hours,
                filming_required=profile.filming_required,
                external_guests_required=profile.external_guests_required,
                editing_complexity=profile.editing_complexity,
                has_product_access=bool(profile.access_to_products_json),
                requires_product_access=requires_product_access,
                weekday_publish_only=profile.weekday_publish_only,
                content_calendar=profile.content_calendar_json,
            )
            components["production_feasibility_v2"] = {
                "feasibility": feasibility.feasibility,
                "feasible_for_act": feasibility.feasible_for_act,
                "estimated_days_min": feasibility.estimated_days_min,
                "estimated_days_max": feasibility.estimated_days_max,
                "recommended_publish_by": (feasibility.recommended_publish_by.isoformat()),
                "reason_codes": list(feasibility.reason_codes),
                "version": feasibility.version,
            }
            components["reason_codes"] = [
                *reason_codes,
                *feasibility.reason_codes,
            ]
        opportunities = self._opportunities(
            profile=profile,
            signal=signal,
            angles=opportunity_angles,
            score=score,
            strongest=strongest,
            observed_at=observed_at,
            feasibility=feasibility,
        )
        return ChannelFitResult(
            score=score,
            components=components,
            opportunities=opportunities,
            content_gap_map=content_gap_map,
        )

    @staticmethod
    def _opportunities(
        *,
        profile: ChannelProfile,
        signal: Signal,
        angles: list[dict[str, object]],
        score: float,
        strongest: list[tuple[str, float]],
        observed_at: datetime,
        feasibility: FeasibilityAssessment | None = None,
    ) -> list[dict[str, object]]:
        earliest = observed_at + timedelta(days=profile.production_days_min)
        best_start = max(_aware(signal.opportunity_start), earliest)
        best_end = min(
            _aware(signal.opportunity_end),
            _aware(feasibility.recommended_publish_by)
            if feasibility is not None
            else _aware(signal.opportunity_end),
        )
        feasible = best_start <= best_end
        if not feasible:
            best_start = observed_at
        confidence = (
            "High" if feasible and score >= 75 else "Medium" if feasible and score >= 50 else "Low"
        )
        results: list[dict[str, object]] = []
        for rank, angle in enumerate(angles, start=1):
            opportunity_id = str(
                uuid5(
                    NAMESPACE_URL,
                    f"opportunity:{profile.workspace_id}:{signal.id}:{rank}:{FIT_VERSION}",
                )
            )
            results.append(
                {
                    **angle,
                    "opportunity_id": opportunity_id,
                    "rank": rank,
                    "status": "active",
                    "channel_fit_score": score,
                    "opportunity_confidence": confidence,
                    "best_publish_window": {
                        "start": best_start.isoformat(),
                        "end": best_end.isoformat(),
                        "label": _window_label(best_start, best_end, observed_at),
                    },
                    "expected_breakout_window": {
                        "start": _aware(signal.opportunity_start).isoformat(),
                        "end": _aware(signal.opportunity_end).isoformat(),
                    },
                    "expected_saturation_window": {
                        "start": _aware(signal.opportunity_end).isoformat(),
                        "end": (_aware(signal.opportunity_end) + timedelta(days=7)).isoformat(),
                    },
                    "production_time_days": {
                        "min": (
                            feasibility.estimated_days_min
                            if feasibility is not None
                            else profile.production_days_min
                        ),
                        "max": (
                            feasibility.estimated_days_max
                            if feasibility is not None
                            else profile.production_days_max
                        ),
                    },
                    **(
                        {
                            "recommended_publish_by": (
                                feasibility.recommended_publish_by.isoformat()
                            ),
                            "recommended_publish_by_label": (
                                feasibility.recommended_publish_by_label
                            ),
                            "feasibility": feasibility.feasibility,
                            "feasible_for_act": feasibility.feasible_for_act,
                            "infeasibility_reasons": list(feasibility.reason_codes),
                            "decay_days": feasibility.decay_days,
                            "decay_version": feasibility.version,
                            "timezone": feasibility.timezone,
                        }
                        if feasibility is not None
                        else {}
                    ),
                    "fit_reasons": [
                        f"{key.replace('_', ' ')}: {value:.0f}/100" for key, value in strongest
                    ],
                }
            )
        return results
