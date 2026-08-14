from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from apps.api.models import (
    ChannelProfile,
    VideoFeature,
    WorkspaceChannel,
    YoutubeChannel,
    YoutubeVideo,
)
from packages.channel_profile import (
    CHANNEL_PROFILE_VERSION,
    ChannelProfileInference,
    ChannelVideoSample,
    extract_channel_profile_v2,
)


def primary_owned_channel(
    session: Session,
    workspace_id: str,
) -> WorkspaceChannel | None:
    return session.scalar(
        select(WorkspaceChannel)
        .where(
            WorkspaceChannel.workspace_id == workspace_id,
            WorkspaceChannel.relationship == "owned",
            WorkspaceChannel.active.is_(True),
        )
        .order_by(WorkspaceChannel.priority)
        .limit(1)
    )


def _inference(
    session: Session,
    *,
    channel: YoutubeChannel,
    captured_at: datetime,
) -> ChannelProfileInference:
    videos = list(
        session.scalars(
            select(YoutubeVideo)
            .where(YoutubeVideo.channel_id == channel.id)
            .order_by(desc(YoutubeVideo.published_at))
            .limit(80)
        )
    )
    samples: list[ChannelVideoSample] = []
    for video in videos:
        feature = session.scalar(
            select(VideoFeature)
            .where(VideoFeature.video_id == video.id)
            .order_by(desc(VideoFeature.calculated_at))
            .limit(1)
        )
        samples.append(
            ChannelVideoSample(
                id=video.id,
                title=video.title,
                description=video.description,
                published_at=video.published_at,
                duration_seconds=video.duration_seconds,
                is_short=video.is_short,
                is_live=video.is_live,
                outlier_ratio=feature.outlier_ratio if feature is not None else None,
            )
        )
    return extract_channel_profile_v2(
        channel_title=channel.title,
        channel_description=channel.description,
        samples=samples,
        captured_at=captured_at,
    )


def ensure_channel_profile(
    session: Session,
    owned: WorkspaceChannel,
) -> ChannelProfile:
    existing = session.get(ChannelProfile, (owned.workspace_id, owned.channel_id))
    channel = session.get(YoutubeChannel, owned.channel_id)
    if channel is None:
        raise RuntimeError("Owned channel does not exist")
    if (
        existing is not None
        and existing.profile_version == CHANNEL_PROFILE_VERSION
        and existing.inference_json
    ):
        return existing

    now = datetime.now(tz=UTC)
    inferred = _inference(session, channel=channel, captured_at=now)
    inference_json = {
        "core_topics": list(inferred.core_topics),
        "adjacent_topics": list(inferred.adjacent_topics),
        "legacy_topics": list(inferred.legacy_topics),
        "preferred_formats": list(inferred.preferred_formats),
        "successful_formats": list(inferred.successful_formats),
        "typical_duration": {
            "min_seconds": inferred.typical_duration_min_seconds,
            "max_seconds": inferred.typical_duration_max_seconds,
        },
        "upload_cadence": inferred.upload_cadence,
        "audience_sophistication": inferred.audience_sophistication,
        "creator_authority": inferred.creator_authority,
        "title_style": inferred.title_style,
        "version": inferred.version,
    }
    if existing is None:
        profile = ChannelProfile(
            workspace_id=owned.workspace_id,
            channel_id=owned.channel_id,
            profile_source=(
                "demo" if channel.youtube_channel_id.startswith("UCESDEMO") else "inferred"
            ),
            audience_description=inferred.cleaned_channel_description,
            geography=channel.country or "US",
            language=channel.default_language or "en",
            topic_keywords_json=[
                *inferred.core_topics,
                *inferred.adjacent_topics,
            ],
            preferred_formats_json=list(inferred.preferred_formats),
            creator_expertise_json=list(inferred.core_topics[:8]),
            production_capabilities_json=[
                "screen recording",
                "software testing",
                "technical explanation",
            ],
            exclusions_json=[],
            strategic_goals_json=[
                "publish evidence-backed AI/technology coverage",
                "differentiate with practical testing",
            ],
            title_style_json=inferred.title_style,
            normal_duration_min_seconds=inferred.typical_duration_min_seconds,
            normal_duration_max_seconds=inferred.typical_duration_max_seconds,
            production_days_min=3,
            production_days_max=7,
            core_topics_json=list(inferred.core_topics),
            adjacent_topics_json=list(inferred.adjacent_topics),
            legacy_topics_json=list(inferred.legacy_topics),
            successful_formats_json=list(inferred.successful_formats),
            upload_cadence_json=inferred.upload_cadence,
            audience_sophistication=inferred.audience_sophistication,
            creator_authority=inferred.creator_authority,
            risk_tolerance="balanced",
            team_size=1,
            research_capacity_hours=8,
            filming_required=False,
            external_guests_required=False,
            editing_complexity="medium",
            access_to_products_json=[],
            experiment_level="balanced",
            evergreen_trend_balance=0.5,
            weekday_publish_only=False,
            content_calendar_json=[],
            inference_json=inference_json,
            explicit_overrides_json={},
            profile_version=CHANNEL_PROFILE_VERSION,
            created_at=now,
            updated_at=now,
        )
        session.add(profile)
        session.flush()
        return profile

    existing.core_topics_json = list(inferred.core_topics)
    existing.adjacent_topics_json = list(inferred.adjacent_topics)
    existing.legacy_topics_json = list(inferred.legacy_topics)
    existing.successful_formats_json = list(inferred.successful_formats)
    existing.upload_cadence_json = inferred.upload_cadence
    existing.inference_json = inference_json
    existing.profile_version = CHANNEL_PROFILE_VERSION
    if existing.profile_source != "user":
        existing.audience_description = inferred.cleaned_channel_description
        existing.topic_keywords_json = [
            *inferred.core_topics,
            *inferred.adjacent_topics,
        ]
        existing.preferred_formats_json = list(inferred.preferred_formats)
        existing.creator_expertise_json = list(inferred.core_topics[:8])
        existing.title_style_json = inferred.title_style
        existing.normal_duration_min_seconds = inferred.typical_duration_min_seconds
        existing.normal_duration_max_seconds = inferred.typical_duration_max_seconds
        existing.audience_sophistication = inferred.audience_sophistication
        existing.creator_authority = inferred.creator_authority
    existing.updated_at = now
    session.flush()
    return existing
