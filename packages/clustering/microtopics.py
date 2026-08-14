from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from hashlib import sha256
from typing import Literal

from packages.clustering.semantic import PRODUCT_ENTITIES, normalize_entities

DOMAIN_PRIORITY = (
    "AI video generation",
    "AI robotics",
    "Chinese AI models",
    "Developer tools",
    "Coding agents",
    "AI agents",
    "AI models",
    "AI productivity",
    "Productivity",
)

_GENERIC_DOMAINS = {
    "AI agents",
    "AI models",
    "AI productivity",
    "Productivity",
}

MICROTOPIC_V5_VERSION = "microtopic-clustering-v5"


@dataclass(frozen=True)
class FacetDefinition:
    key: str
    label_prefix: str
    patterns: tuple[str, ...]


FACETS: tuple[FacetDefinition, ...] = (
    FacetDefinition(
        key="free_local",
        label_prefix="Free, local and unlimited",
        patterns=(
            "free",
            "unlimited",
            "no paywall",
            "on your pc",
            "100% local",
            "local ai",
            "consumer gpu",
        ),
    ),
    FacetDefinition(
        key="beginner_no_code",
        label_prefix="Beginner and no-code",
        patterns=(
            "beginner",
            "first ai",
            "zero to",
            "no code",
            "no-code",
            "no coding",
            "without coding",
            "full course",
            "in 15 minutes",
            "in 14 minutes",
        ),
    ),
    FacetDefinition(
        key="applied_workflows",
        label_prefix="Task-specific",
        patterns=(
            "recurring task",
            "for companies",
            "for teams",
            "business",
            "making $",
            "make money",
            "day trades",
            "trading",
            "real workflow",
            "worst task",
        ),
    ),
    FacetDefinition(
        key="production_deployment",
        label_prefix="Production and deployment",
        patterns=(
            "in production",
            "production workflow",
            "deployment",
            "multi-agent",
            "real project",
        ),
    ),
    FacetDefinition(
        key="open_source",
        label_prefix="Open-source",
        patterns=("open source", "open-source", "self-hosted", "self hosted"),
    ),
    FacetDefinition(
        key="release_wave",
        label_prefix="Newly released",
        patterns=(
            "new model",
            "new models",
            "new ai",
            "release",
            "is here",
            "changed everything",
            "panicking",
            "breakthrough",
            "deepseek moment",
        ),
    ),
    FacetDefinition(
        key="comparison",
        label_prefix="Compared",
        patterns=(
            "compare",
            "compared",
            "comparison",
            " versus ",
            " vs ",
            "best ",
            "the last ",
        ),
    ),
    FacetDefinition(
        key="security_failure",
        label_prefix="Security failures in",
        patterns=("rogue", "hacked", "security failure", "unsafe", "jailbreak"),
    ),
)


@dataclass(frozen=True)
class MicrotopicDocument:
    id: str
    title: str
    description: str
    entities: tuple[str, ...]


@dataclass(frozen=True)
class MicrotopicCluster:
    key: str
    label: str
    aliases: tuple[str, ...]
    entities: tuple[str, ...]
    document_ids: tuple[str, ...]
    specificity_score: float
    facet: str
    domain: str = ""
    primary_entity: str = ""
    secondary_entities: tuple[str, ...] = ()
    audience: str = ""
    user_problem: str = ""
    core_claim: str = ""
    workflow_context: str = ""
    format_distribution: tuple[tuple[str, float], ...] = ()
    thesis: str = ""
    thesis_support_ratio: float = 0
    visible: bool = True
    reason_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class MicrotopicIdentity:
    domain: str
    facet: str
    primary_entity: str
    secondary_entities: tuple[str, ...]
    audience: str
    user_problem: str
    core_claim: str
    workflow_context: str
    content_format: str


@dataclass(frozen=True)
class TopicRelationshipDecision:
    action: Literal["split", "merge", "keep_separate", "reject"]
    reason_codes: tuple[str, ...]


def _domain(entities: tuple[str, ...], text: str = "") -> str | None:
    values = [entity for entity in DOMAIN_PRIORITY if entity in set(entities)]
    if not values:
        return None
    lowered = text.lower()
    priority = {entity: index for index, entity in enumerate(DOMAIN_PRIORITY)}

    def mentioned(entity: str) -> bool:
        phrase = entity.lower()
        if phrase in lowered:
            return True
        words = phrase.split()
        if words and words[-1].endswith("s"):
            return " ".join((*words[:-1], words[-1][:-1])) in lowered
        return False

    return max(
        values,
        key=lambda entity: (
            mentioned(entity),
            entity not in _GENERIC_DOMAINS,
            len(entity.split()),
            -priority[entity],
        ),
    )


def _facets(text: str) -> tuple[FacetDefinition, ...]:
    lowered = f" {text.lower()} "
    return tuple(facet for facet in FACETS if any(pattern in lowered for pattern in facet.patterns))


def _product_anchor(document: MicrotopicDocument, facet: FacetDefinition) -> str | None:
    products = [
        entity for entity in normalize_entities(document.title, "") if entity in PRODUCT_ENTITIES
    ]
    if facet.key == "comparison" and len(products) >= 2:
        return " vs ".join(products[:2])
    return products[0] if products else None


def _label(
    *,
    domain: str,
    facet: FacetDefinition,
    anchor: str | None,
) -> str:
    if anchor is None:
        return f"{facet.label_prefix} {domain}"
    if facet.key == "release_wave":
        return f"New {anchor} release"
    if facet.key == "comparison":
        return f"{anchor} comparison"
    return f"{facet.label_prefix} {anchor} {domain.lower()}"


def cluster_microtopics(
    documents: list[MicrotopicDocument],
) -> list[MicrotopicCluster]:
    grouped: defaultdict[tuple[str, str, str], list[MicrotopicDocument]] = defaultdict(list)
    facets_by_key: dict[tuple[str, str, str], FacetDefinition] = {}
    for document in documents:
        domain = _domain(document.entities, document.title)
        facets = _facets(document.title)
        if domain is None or not facets:
            continue
        facet = facets[0]
        anchor = _product_anchor(document, facet)
        if anchor is None and facet.key in {"release_wave", "comparison"}:
            continue
        anchor_key = anchor or "generic"
        key = (domain, facet.key, anchor_key)
        grouped[key].append(document)
        facets_by_key[key] = facet

    clusters: list[MicrotopicCluster] = []
    for (domain, facet_key, anchor_key), members in grouped.items():
        facet = facets_by_key[(domain, facet_key, anchor_key)]
        anchor = None if anchor_key == "generic" else anchor_key
        entity_counts = Counter(entity for member in members for entity in member.entities)
        entities = tuple(
            dict.fromkeys(
                (
                    domain,
                    *((anchor,) if anchor else ()),
                    *(
                        entity
                        for entity, count in entity_counts.most_common()
                        if entity not in {domain, anchor} and count >= 2
                    ),
                )
            )
        )
        label = _label(domain=domain, facet=facet, anchor=anchor)
        fingerprint = "|".join((domain.lower(), facet_key, anchor_key.lower()))
        stable_key = f"micro-{sha256(fingerprint.encode()).hexdigest()[:18]}"
        distinct_documents = tuple(dict.fromkeys(member.id for member in members))
        specificity = min(
            100.0,
            56.0
            + min(len(distinct_documents), 6) * 4
            + min(len(entities), 3) * 5
            + (12 if anchor else 0),
        )
        clusters.append(
            MicrotopicCluster(
                key=stable_key,
                label=label,
                aliases=(f"{facet.label_prefix} {domain}",),
                entities=entities,
                document_ids=distinct_documents,
                specificity_score=round(specificity, 1),
                facet=facet_key,
            )
        )
    return sorted(
        clusters,
        key=lambda cluster: (-len(cluster.document_ids), cluster.label),
    )


def _matches(text: str, *patterns: str) -> bool:
    lowered = f" {text.lower()} "
    return any(pattern in lowered for pattern in patterns)


def _audience(text: str) -> str:
    if _matches(text, " business", " company", " companies", " team", " recurring"):
        return "business teams"
    if _matches(text, " beginner", " no code", " no-code", " without coding"):
        return "non-technical beginners"
    if _matches(text, " developer", " codebase", " repo", " cli", " api "):
        return "developers"
    if _matches(text, " creator", " youtube", " video workflow", " content"):
        return "creators"
    return "AI practitioners"


def _user_problem(text: str) -> str:
    if _matches(text, " private repo", " safety", " safe ", " permission", " guardrail"):
        return "grant autonomous tools access without losing control"
    if _matches(text, " spending", " purchase", " buying", " refund", " transaction"):
        return "control autonomous purchases and reversals"
    if _matches(text, " recurring", " manual task", " worst task", " repetitive", " business"):
        return "automate recurring business work"
    if _matches(text, " local ", " gpu", " subscription", " paywall", " self-host"):
        return "reduce recurring AI infrastructure cost"
    if _matches(text, " benchmark", " leaderboard", " compare", " vs "):
        return "choose between competing products using practical proof"
    if _matches(text, " deploy", " production", " real project"):
        return "move an experimental workflow into production"
    return "understand practical trade-offs"


def _core_claim(text: str) -> str:
    if _matches(text, " local ", " on your pc", " consumer gpu", " self-host"):
        return "run the workflow locally"
    if _matches(text, " without subscription", " free ", " unlimited", " no paywall"):
        return "avoid recurring subscriptions"
    if _matches(text, " autonomous", " end-to-end", " whole workflow", " multi-agent"):
        return "complete the workflow end to end"
    if _matches(text, " no code", " no-code", " without coding", " beginner"):
        return "adopt the workflow without coding"
    if _matches(text, " safe ", " guardrail", " permission", " private repo"):
        return "keep autonomous execution controlled"
    if _matches(text, " faster", " automate", " recurring", " productivity"):
        return "replace repetitive work with a repeatable automation"
    if _matches(text, " benchmark", " stress test", " real-world", " real world"):
        return "separate practical performance from leaderboard claims"
    return "deliver a measurable practical outcome"


def _workflow_context(text: str) -> str:
    if _matches(text, " private repo", " codebase", " developer", " cli"):
        return "software delivery"
    if _matches(text, " purchase", " buying", " shopping", " transaction"):
        return "shopping and transaction control"
    if _matches(text, " recurring", " business", " company", " team"):
        return "recurring business operations"
    if _matches(text, " local ", " gpu", " self-host", " on your pc"):
        return "local production setup"
    if _matches(text, " production", " deploy", " real project"):
        return "production deployment"
    if _matches(text, " video", " creator", " youtube"):
        return "creator production"
    return "practical day-to-day use"


def _content_format(text: str) -> str:
    if _matches(text, " benchmark", " stress test", " tested ", " test "):
        return "hands-on test"
    if _matches(text, " compare", " comparison", " vs ", " versus ", " best "):
        return "structured comparison"
    if _matches(text, " how to", " tutorial", " guide", " course", " build "):
        return "tutorial"
    if _matches(text, " case study", " diary", " for 7 days", " real project"):
        return "case study"
    if _matches(text, " release", " is here", " announcement", " new model"):
        return "release explainer"
    return "evidence-led explainer"


def infer_microtopic_identity(document: MicrotopicDocument) -> MicrotopicIdentity | None:
    text = " ".join((document.title, document.description[:1_200]))
    domain = _domain(document.entities, text)
    if domain is None:
        return None
    facets = _facets(text)
    facet = facets[0] if facets else None
    normalized = normalize_entities(document.title, document.description)
    products = tuple(entity for entity in normalized if entity in PRODUCT_ENTITIES)
    primary = products[0] if products else domain
    secondary = tuple(
        dict.fromkeys((*products[1:], *(e for e in document.entities if e != primary)))
    )
    return MicrotopicIdentity(
        domain=domain,
        facet=facet.key if facet else "subject",
        primary_entity=primary,
        secondary_entities=secondary,
        audience=_audience(text),
        user_problem=_user_problem(text),
        core_claim=_core_claim(text),
        workflow_context=_workflow_context(text),
        content_format=_content_format(text),
    )


def compare_microtopic_identities(
    first: MicrotopicIdentity | None,
    second: MicrotopicIdentity | None,
    *,
    semantic_overlap: float,
    publication_gap_days: float,
) -> TopicRelationshipDecision:
    if first is None or second is None:
        return TopicRelationshipDecision("reject", ("missing_topic_identity",))
    split_reasons: list[str] = []
    if first.primary_entity != second.primary_entity:
        split_reasons.append("different_primary_entity")
    if first.user_problem != second.user_problem:
        split_reasons.append("different_user_problem")
    if first.audience != second.audience:
        split_reasons.append("different_target_audience")
    if first.core_claim != second.core_claim:
        split_reasons.append("incompatible_core_claim")
    if split_reasons:
        return TopicRelationshipDecision("split", tuple(split_reasons))
    if semantic_overlap >= 0.75 and publication_gap_days <= 14:
        return TopicRelationshipDecision(
            "merge",
            ("same_identity", "strong_semantic_overlap", "shared_temporal_window"),
        )
    return TopicRelationshipDecision(
        "keep_separate",
        ("weak_semantic_or_temporal_overlap",),
    )


def _v5_label(identity: MicrotopicIdentity) -> str:
    entity = identity.primary_entity
    if (
        identity.audience == "business teams"
        and identity.core_claim == "adopt the workflow without coding"
    ):
        return f"No-code {entity} for recurring business tasks"
    if identity.core_claim == "run the workflow locally":
        return f"{entity} for local workflows on owned hardware"
    if identity.core_claim == "avoid recurring subscriptions":
        return f"{entity} workflows without recurring subscriptions"
    if identity.core_claim == "complete the workflow end to end":
        return f"{entity} for end-to-end {identity.workflow_context}"
    if identity.core_claim == "keep autonomous execution controlled":
        return f"{entity} with controlled access for {identity.workflow_context}"
    return f"{entity}: {identity.core_claim} for {identity.audience}"


def _identity_specificity(
    identity: MicrotopicIdentity,
    *,
    document_count: int,
) -> float:
    generic_problem = identity.user_problem == "understand practical trade-offs"
    generic_claim = identity.core_claim == "deliver a measurable practical outcome"
    generic_context = identity.workflow_context == "practical day-to-day use"
    score = 28.0
    score += 12 if identity.primary_entity in PRODUCT_ENTITIES else 7
    score += 12 if not generic_problem else 0
    score += 12 if not generic_claim else 0
    score += 9 if identity.audience != "AI practitioners" else 3
    score += 11 if not generic_context else 0
    score += 7 if identity.content_format != "evidence-led explainer" else 3
    score += min(9, document_count * 3)
    return round(min(100.0, score), 1)


def cluster_microtopics_v5(
    documents: list[MicrotopicDocument],
) -> list[MicrotopicCluster]:
    identities: dict[str, MicrotopicIdentity] = {}
    grouped: defaultdict[tuple[str, ...], list[MicrotopicDocument]] = defaultdict(list)
    for document in documents:
        identity = infer_microtopic_identity(document)
        if identity is None:
            continue
        identities[document.id] = identity
        identity_key = (
            identity.domain,
            identity.facet,
            identity.primary_entity,
            identity.audience,
            identity.user_problem,
            identity.core_claim,
            identity.workflow_context,
        )
        grouped[identity_key].append(document)

    clusters: list[MicrotopicCluster] = []
    for group_key, members in grouped.items():
        identity = identities[members[0].id]
        formats = Counter(identities[member.id].content_format for member in members)
        total = max(1, len(members))
        format_distribution = tuple(
            (name, round(count / total, 3)) for name, count in formats.most_common()
        )
        specificity = _identity_specificity(identity, document_count=len(members))
        release_or_comparison = identity.facet in {"release_wave", "comparison"}
        has_product_anchor = identity.primary_entity in PRODUCT_ENTITIES
        broad_only = (
            identity.user_problem == "understand practical trade-offs"
            and identity.core_claim == "deliver a measurable practical outcome"
            and identity.workflow_context == "practical day-to-day use"
        )
        reasons: list[str] = []
        if release_or_comparison and not has_product_anchor:
            reasons.append("missing_product_anchor")
        if broad_only:
            reasons.append("broad_domain_or_facet_only")
        if specificity < 70:
            reasons.append("specificity_below_visible_floor")
        support_ratio = 1.0
        visible = not reasons and support_ratio >= 0.8
        label = _v5_label(identity)
        fingerprint = "|".join(value.lower() for value in group_key)
        stable_key = f"micro-v5-{sha256(fingerprint.encode()).hexdigest()[:18]}"
        thesis = (
            f"For {identity.audience} trying to {identity.user_problem}, "
            f"{identity.primary_entity} now promises to {identity.core_claim} "
            f"in {identity.workflow_context}; {len(members)} stored evidence "
            "videos support the emerging pattern."
        )
        clusters.append(
            MicrotopicCluster(
                key=stable_key,
                label=label,
                aliases=(label, f"{identity.primary_entity} {identity.user_problem}"),
                entities=tuple(
                    dict.fromkeys(
                        (
                            identity.primary_entity,
                            *identity.secondary_entities,
                            identity.domain,
                        )
                    )
                ),
                document_ids=tuple(dict.fromkeys(member.id for member in members)),
                specificity_score=specificity,
                facet=identity.facet,
                domain=identity.domain,
                primary_entity=identity.primary_entity,
                secondary_entities=identity.secondary_entities,
                audience=identity.audience,
                user_problem=identity.user_problem,
                core_claim=identity.core_claim,
                workflow_context=identity.workflow_context,
                format_distribution=format_distribution,
                thesis=thesis,
                thesis_support_ratio=support_ratio,
                visible=visible,
                reason_codes=tuple(reasons or ("identity_supported",)),
            )
        )
    return sorted(
        clusters,
        key=lambda cluster: (
            not cluster.visible,
            -len(cluster.document_ids),
            -cluster.specificity_score,
            cluster.label,
        ),
    )
