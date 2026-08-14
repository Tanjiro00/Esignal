from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceItem(StrictModel):
    ref: str = Field(min_length=3, max_length=180)
    kind: Literal["video", "transcript", "comment", "metric"]
    title: str = Field(min_length=1, max_length=500)
    text: str = Field(min_length=1, max_length=2_000)


class ChannelDiscoveryQuery(StrictModel):
    query: str = Field(min_length=8, max_length=120)
    category: str = Field(min_length=3, max_length=80)
    rationale: str = Field(min_length=12, max_length=400)
    evidence_refs: list[str] = Field(min_length=1, max_length=8)


class ChannelDiscoveryPlan(StrictModel):
    audience_description: str = Field(min_length=12, max_length=500)
    core_topics: list[str] = Field(min_length=3, max_length=8)
    adjacent_topics: list[str] = Field(min_length=3, max_length=8)
    queries: list[ChannelDiscoveryQuery] = Field(min_length=10, max_length=20)


class TopicCandidate(StrictModel):
    key: str = Field(min_length=3, max_length=160)
    current_label: str = Field(min_length=3, max_length=300)
    aliases: list[str] = Field(max_length=12)
    facet: str = Field(min_length=1, max_length=80)
    domain: str = Field(max_length=120)
    primary_entity: str = Field(max_length=120)
    audience: str = Field(max_length=160)
    user_problem: str = Field(max_length=240)
    core_claim: str = Field(max_length=240)
    evidence_refs: list[str] = Field(min_length=1, max_length=24)


class ReconciledTopic(StrictModel):
    member_keys: list[str] = Field(min_length=1, max_length=12)
    canonical_label: str = Field(min_length=3, max_length=120)
    aliases: list[str] = Field(max_length=12)
    rationale: str = Field(min_length=3, max_length=500)
    evidence_refs: list[str] = Field(min_length=1, max_length=24)


class TopicReconciliation(StrictModel):
    topics: list[ReconciledTopic] = Field(min_length=1, max_length=40)


class GroundedClaim(StrictModel):
    text: str = Field(min_length=3, max_length=500)
    evidence_refs: list[str] = Field(min_length=1, max_length=12)


class TopicSynthesis(StrictModel):
    canonical_label: str = Field(min_length=3, max_length=120)
    aliases: list[str] = Field(max_length=12)
    thesis: str = Field(min_length=20, max_length=900)
    why_growing: list[GroundedClaim] = Field(min_length=2, max_length=5)


class ShadowEvidenceDossier(StrictModel):
    observed_pattern: str = Field(min_length=20, max_length=700)
    supporting_families: list[GroundedClaim] = Field(min_length=2, max_length=5)
    contradictions: list[GroundedClaim] = Field(max_length=4)
    uncertainty: str = Field(min_length=12, max_length=500)


class ShadowTrendTaxonomy(StrictModel):
    neutral_label: str = Field(min_length=3, max_length=120)
    rationale: str = Field(min_length=12, max_length=500)
    evidence_refs: list[str] = Field(min_length=2, max_length=16)


class ShadowTrendAudit(StrictModel):
    decision: Literal["accept_to_shadow", "watch", "reject"]
    summary: str = Field(min_length=12, max_length=700)
    specificity: Literal["narrow_subject", "broad_category"]
    independent_support: bool
    copy_wave_risk: Literal["low", "medium", "high"]
    language_scope: Literal["english", "mixed", "non_english"]
    format_neutral: bool
    evidence_refs: list[str] = Field(min_length=2, max_length=16)
    reason_codes: list[str] = Field(min_length=1, max_length=12)


class ContentGapEdit(StrictModel):
    gap_key: str = Field(min_length=3, max_length=160)
    title: str = Field(min_length=8, max_length=180)
    audience_promise: str = Field(min_length=12, max_length=500)
    why_now: str = Field(min_length=12, max_length=500)
    differentiation: str = Field(min_length=12, max_length=500)
    title_directions: list[str] = Field(min_length=2, max_length=5)
    evidence_refs: list[str] = Field(min_length=1, max_length=16)


class ContentGapSynthesis(StrictModel):
    gaps: list[ContentGapEdit] = Field(min_length=1, max_length=3)


class EvidenceInsight(StrictModel):
    topic: str = Field(min_length=8, max_length=180)
    statement: str = Field(min_length=20, max_length=700)
    why_non_obvious: str = Field(min_length=20, max_length=700)
    creator_question: str = Field(min_length=8, max_length=240)
    insight_kind: Literal[
        "contradiction",
        "behavior_shift",
        "constraint",
        "adoption_pattern",
        "market_structure",
    ]
    evidence_refs: list[str] = Field(min_length=2, max_length=16)


class EvidenceInsightSynthesis(StrictModel):
    insight: EvidenceInsight | None
    no_insight_reason: str = Field(max_length=500)


class GroundingCheck(StrictModel):
    target: str = Field(min_length=3, max_length=180)
    verdict: Literal["supported", "overstated", "unsupported", "scope_mismatch"]
    rationale: str = Field(min_length=3, max_length=500)
    evidence_refs: list[str] = Field(min_length=1, max_length=16)


class GroundingAudit(StrictModel):
    decision: Literal["accept", "reject"]
    summary: str = Field(min_length=3, max_length=700)
    checks: list[GroundingCheck] = Field(min_length=1, max_length=20)


class InsightReleaseAudit(StrictModel):
    decision: Literal["accept", "reject"]
    summary: str = Field(min_length=3, max_length=700)
    checks: list[GroundingCheck] = Field(min_length=1, max_length=20)
    non_obviousness: Literal["strong", "borderline", "obvious"]
    decision_value: Literal["changes_creator_decision", "adds_context_only", "none"]
    specificity: Literal["specific_mechanism", "broad_claim"]
    generic_restatement: bool
    decision_change: str = Field(min_length=12, max_length=500)
    evidence_refs: list[str] = Field(min_length=2, max_length=16)
