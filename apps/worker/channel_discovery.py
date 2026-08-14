from __future__ import annotations

import re
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from apps.api.channel_profiles import ensure_channel_profile, primary_owned_channel
from apps.api.config import Settings
from apps.api.models import (
    ChannelProfile,
    DiscoveryQueryRecord,
    WorkspaceDiscoveryQuery,
    YoutubeChannel,
    YoutubeVideo,
)
from apps.worker.llm_intelligence import LLMIntelligenceService
from packages.llm_intelligence import (
    ChannelDiscoveryPlan,
    ChannelDiscoveryQuery,
    EvidenceItem,
)

CHANNEL_DISCOVERY_VERSION = "channel-discovery-v2-profile-grounded"
_GENERIC_QUERIES = {
    "ai agents",
    "ai models",
    "ai tools",
    "ai trends",
    "new ai",
    "new ai models",
    "new ai tools",
}
_LOW_VALUE_ANCHORS = {
    "castello",
    "cdn",
    "composite",
    "cookies",
    "erid",
    "itzy",
    "shorts",
    "unionconf",
    "youtu",
    "youtube",
}
_KNOWN_SINGLE_TOPIC_ANCHORS = {
    "c++",
    "cybersecurity",
    "devops",
    "python",
    "react",
    "saas",
}

_DEFAULT_TOPIC_ANCHORS = (
    "AI software engineering",
    "developer careers and hiring",
    "AI model economics",
    "local AI hardware",
    "AI video creation",
)

_DISCOVERY_LENSES = (
    ("recent adoption evidence", "Early movement"),
    ("independent benchmark results", "Performance evidence"),
    ("failure conditions limitations", "Constraints"),
    ("audience demand questions", "Audience demand"),
)


def _clean_query(value: str) -> str:
    return " ".join(value.strip().split())


def _valid_query(value: str) -> bool:
    normalized = _clean_query(value).lower()
    words = normalized.split()
    return (
        3 <= len(words) <= 10
        and normalized not in _GENERIC_QUERIES
        and all(character.isascii() for character in normalized)
    )


def _topic_anchor(value: str) -> str:
    words = [
        word
        for word in _clean_query(value).split()
        if word.lower() not in {"the", "and", "news", "latest", "review", "video"}
    ]
    return " ".join(words[:5])


def _valid_anchor(value: str) -> bool:
    normalized = _topic_anchor(value).lower()
    words = normalized.split()
    if not normalized or not all(character.isascii() for character in normalized):
        return False
    if any(word in _LOW_VALUE_ANCHORS for word in words):
        return False
    if any(re.search(r"[a-z]", word) and re.search(r"\d", word) for word in words):
        return False
    if any(
        len(word) >= 8 and not any(vowel in word for vowel in ("a", "e", "i", "o", "u", "y"))
        for word in words
    ):
        return False
    return len(words) >= 2 or normalized in _KNOWN_SINGLE_TOPIC_ANCHORS


def _fallback_plan(
    evidence_ref: str,
    *,
    audience_description: str = "",
    topic_keywords: tuple[str, ...] = (),
    creator_expertise: tuple[str, ...] = (),
    core_topics: tuple[str, ...] = (),
    adjacent_topics: tuple[str, ...] = (),
) -> ChannelDiscoveryPlan:
    anchors = tuple(
        dict.fromkeys(
            anchor
            for value in (
                *topic_keywords,
                *creator_expertise,
                *core_topics,
                *adjacent_topics,
            )
            if (anchor := _topic_anchor(value))
            and _valid_anchor(anchor)
            and anchor.lower() not in _GENERIC_QUERIES
        )
    )
    if len(anchors) < 5:
        anchors = tuple(dict.fromkeys((*anchors, *_DEFAULT_TOPIC_ANCHORS)))
    core = list(anchors[:8])
    if len(core) < 3:
        core = list(dict.fromkeys((*core, *_DEFAULT_TOPIC_ANCHORS)))[:3]
    adjacent = list(
        dict.fromkeys(
            (
                *(anchor for anchor in anchors if anchor not in core),
                *(anchor for anchor in _DEFAULT_TOPIC_ANCHORS if anchor not in core),
            )
        )
    )[:8]
    if len(adjacent) < 3:
        adjacent = list(dict.fromkeys((*adjacent, *anchors, *_DEFAULT_TOPIC_ANCHORS)))[:3]
    queries = [
        ChannelDiscoveryQuery(
            query=f"{anchor} {suffix}",
            category=category,
            rationale=(
                "A profile-grounded discovery lane that tests a different evidence "
                "dimension without assuming a video format."
            ),
            evidence_refs=[evidence_ref],
        )
        for anchor in anchors[:5]
        for suffix, category in _DISCOVERY_LENSES
    ]
    return ChannelDiscoveryPlan(
        audience_description=(
            audience_description
            or "Technology viewers looking for concrete changes, constraints and evidence."
        ),
        core_topics=core,
        adjacent_topics=adjacent,
        queries=queries,
    )


class ChannelDiscoveryService:
    """Build and activate an evidence-linked query portfolio for one workspace."""

    def __init__(
        self,
        session: Session,
        settings: Settings,
        *,
        llm: LLMIntelligenceService | None = None,
    ) -> None:
        self._session = session
        self._settings = settings
        self._llm = llm or LLMIntelligenceService(session, settings)

    def build(self, workspace_id: str) -> ChannelDiscoveryPlan:
        owned = primary_owned_channel(self._session, workspace_id)
        if owned is None:
            raise LookupError("Connect a YouTube channel first")
        channel = self._session.get(YoutubeChannel, owned.channel_id)
        if channel is None:
            raise LookupError("Connected YouTube channel was not found")
        profile = ensure_channel_profile(self._session, owned)
        videos = list(
            self._session.scalars(
                select(YoutubeVideo)
                .where(YoutubeVideo.channel_id == channel.id)
                .order_by(desc(YoutubeVideo.published_at))
                .limit(30)
            )
        )
        channel_ref = f"channel:{channel.id}"
        evidence = [
            EvidenceItem(
                ref=channel_ref,
                kind="metric",
                title=channel.title,
                text=(
                    f"Stored public channel metadata. Description: "
                    f"{channel.description[:1500] or 'not supplied'}"
                ),
            ),
            *[
                EvidenceItem(
                    ref=f"video:{video.id}",
                    kind="video",
                    title=video.title,
                    text=(
                        f"Published {video.published_at.isoformat()}. "
                        f"Description: {video.description[:1400] or 'not supplied'}"
                    ),
                )
                for video in videos
            ],
        ]
        fallback = _fallback_plan(
            channel_ref,
            audience_description=profile.audience_description,
            topic_keywords=tuple(profile.topic_keywords_json),
            creator_expertise=tuple(profile.creator_expertise_json),
            core_topics=tuple(profile.core_topics_json),
            adjacent_topics=tuple(profile.adjacent_topics_json),
        )
        generated = self._llm.plan_channel_discovery(
            workspace_id=workspace_id,
            channel_title=channel.title,
            current_profile={
                "audience_description": profile.audience_description,
                "topic_keywords": profile.topic_keywords_json,
                "creator_expertise": profile.creator_expertise_json,
                "core_topics": profile.core_topics_json,
                "adjacent_topics": profile.adjacent_topics_json,
                "preferred_formats": profile.preferred_formats_json,
            },
            evidence=evidence,
        )
        plan = (
            generated.value
            if generated is not None and isinstance(generated.value, ChannelDiscoveryPlan)
            else fallback
        )
        plan = self._sanitize_plan(plan, fallback=fallback)
        self._apply_profile(profile, plan, llm_run_id=generated.run_id if generated else None)
        self._activate_queries(workspace_id, plan)
        self._session.commit()
        return plan

    def _sanitize_plan(
        self,
        plan: ChannelDiscoveryPlan,
        *,
        fallback: ChannelDiscoveryPlan,
    ) -> ChannelDiscoveryPlan:
        unique: dict[str, ChannelDiscoveryQuery] = {}
        for item in plan.queries:
            query = _clean_query(item.query)
            normalized = query.lower()
            if _valid_query(query) and normalized not in unique:
                unique[normalized] = item.model_copy(update={"query": query})
        if len(unique) < 10:
            for fallback_query in fallback.queries:
                unique.setdefault(fallback_query.query.lower(), fallback_query)
                if len(unique) >= 14:
                    break
        core_topics = list(
            dict.fromkeys(
                anchor
                for value in (*plan.core_topics, *fallback.core_topics)
                if (anchor := _topic_anchor(value)) and _valid_anchor(anchor)
            )
        )[:8]
        adjacent_topics = list(
            dict.fromkeys(
                anchor
                for value in (*plan.adjacent_topics, *fallback.adjacent_topics)
                if (anchor := _topic_anchor(value))
                and _valid_anchor(anchor)
                and anchor not in core_topics
            )
        )[:8]
        return plan.model_copy(
            update={
                "core_topics": core_topics,
                "adjacent_topics": adjacent_topics,
                "queries": list(unique.values())[:20],
            }
        )

    def _apply_profile(
        self,
        profile: ChannelProfile,
        plan: ChannelDiscoveryPlan,
        *,
        llm_run_id: str | None,
    ) -> None:
        inference = dict(profile.inference_json or {})
        inference["discovery_plan"] = {
            "version": CHANNEL_DISCOVERY_VERSION,
            "llm_run_id": llm_run_id,
            "audience_description": plan.audience_description,
            "core_topics": plan.core_topics,
            "adjacent_topics": plan.adjacent_topics,
            "queries": [item.model_dump(mode="json") for item in plan.queries],
            "created_at": datetime.now(tz=UTC).isoformat(),
        }
        profile.inference_json = inference
        if profile.profile_source != "user":
            profile.profile_source = "inferred_llm" if llm_run_id else "inferred"
            profile.audience_description = plan.audience_description
            profile.core_topics_json = list(plan.core_topics)
            profile.adjacent_topics_json = list(plan.adjacent_topics)
            profile.topic_keywords_json = list(
                dict.fromkeys([*plan.core_topics, *plan.adjacent_topics])
            )
            profile.creator_expertise_json = list(plan.core_topics)
        profile.updated_at = datetime.now(tz=UTC)

    def _activate_queries(
        self,
        workspace_id: str,
        plan: ChannelDiscoveryPlan,
    ) -> None:
        now = datetime.now(tz=UTC)
        desired_ids: set[str] = set()
        for item in plan.queries:
            query = _clean_query(item.query)
            row = self._session.scalar(
                select(DiscoveryQueryRecord).where(DiscoveryQueryRecord.query == query)
            )
            if row is None:
                row = DiscoveryQueryRecord(
                    id=str(uuid4()),
                    query=query,
                    category=item.category,
                    priority=1,
                    country="US",
                    language="en",
                    active=True,
                    source="channel_profile",
                    minimum_interval_seconds=3_600,
                    expires_at=None,
                    last_run_at=None,
                    next_run_at=now,
                    historical_yield=0,
                    cost_per_retained_video=0,
                    precision_score=0,
                    precision_sample_size=0,
                    quality_status="unmeasured",
                    last_precision_at=None,
                    created_at=now,
                    updated_at=now,
                )
                self._session.add(row)
                self._session.flush()
            else:
                row.active = True
                row.next_run_at = now
                row.updated_at = now
            desired_ids.add(row.id)
            mapping = self._session.get(WorkspaceDiscoveryQuery, (workspace_id, row.id))
            if mapping is None:
                mapping = WorkspaceDiscoveryQuery(
                    workspace_id=workspace_id,
                    query_id=row.id,
                    source_type="channel_profile",
                    rationale=item.rationale,
                    evidence_refs_json=list(item.evidence_refs),
                    active=True,
                    created_at=now,
                    updated_at=now,
                )
                self._session.add(mapping)
            else:
                mapping.rationale = item.rationale
                mapping.evidence_refs_json = list(item.evidence_refs)
                mapping.active = True
                mapping.updated_at = now
        for mapping in self._session.scalars(
            select(WorkspaceDiscoveryQuery).where(
                WorkspaceDiscoveryQuery.workspace_id == workspace_id,
                WorkspaceDiscoveryQuery.source_type == "channel_profile",
            )
        ):
            if mapping.query_id not in desired_ids:
                mapping.active = False
                mapping.updated_at = now
