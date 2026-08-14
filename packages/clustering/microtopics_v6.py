from __future__ import annotations

import re
from collections import Counter, defaultdict
from hashlib import sha256

from packages.clustering.microtopics import (
    MicrotopicCluster,
    MicrotopicDocument,
    MicrotopicIdentity,
    _audience,
    _content_format,
)
from packages.clustering.semantic import PRODUCT_ENTITIES, normalize_entities

MICROTOPIC_V6_VERSION = "microtopic-clustering-v6-subject-event"

_AI_ANCHOR = re.compile(
    r"(?i)(?<![\w])(?:"
    r"ai|a\.i\.|artificial intelligence|generative ai|llms?|"
    r"large language models?|chatgpt|openai|gpt-?[234](?:\.5|o)?|"
    r"copilot|gemini|claude|anthropic|midjourney|stable diffusion|"
    r"deepfakes?|text-to-video|image-to-video"
    r")(?![\w])"
)

_PRODUCT_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Microsoft 365 Copilot", ("microsoft 365 copilot", "microsoft copilot")),
    ("GPT-4", ("gpt-4", "gpt 4")),
    ("Figure AI", ("figure ai", "figure robot", "figure status update")),
    ("Optimus", ("optimus robot", "tesla optimus")),
    ("Google AI", ("google ai", "google's ai", "google’s ai")),
    ("Galaxy AI", ("galaxy ai",)),
)

_ROBOTICS_MARKERS = (
    "robot",
    "robotics",
    "humanoid",
    "optimus",
    "figure status",
    "learns to walk",
    "learn to walk",
)
_MEDIA_MARKERS = (
    "ai video",
    "video generation",
    "video generator",
    "image generation",
    "image generator",
    "deepfake",
    "text-to-video",
    "image-to-video",
    "midjourney",
    "stable diffusion",
    "sora",
    "veo",
)
_DEVELOPER_MARKERS = (
    "developer",
    "coding",
    "codebase",
    "programming",
    "github copilot",
    "api ",
    " api",
)
_DEVELOPER_PRODUCTS = {
    "Claude Code",
    "Cursor",
    "Microsoft 365 Copilot",
    "Windsurf",
}
_AGENT_MARKERS = (
    "ai agent",
    "agentic",
    "coding agent",
    "autonomous agent",
    "multi-agent",
)


def _contains(text: str, patterns: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(pattern in lowered for pattern in patterns)


def _detected_products(
    title: str,
    text: str,
    normalized: tuple[str, ...],
) -> tuple[str, ...]:
    lowered = text.lower()
    local = [
        canonical
        for canonical, patterns in _PRODUCT_PATTERNS
        if any(pattern in lowered for pattern in patterns)
    ]
    if "google" in title.lower() and _AI_ANCHOR.search(title):
        local.insert(0, "Google AI")
    existing = [entity for entity in normalized if entity in PRODUCT_ENTITIES]
    return tuple(dict.fromkeys((*local, *existing)))


def _domain(
    title: str,
    text: str,
    entities: tuple[str, ...],
    products: tuple[str, ...],
) -> str | None:
    lowered = text.lower()
    title_lowered = title.lower()
    developer_text = re.sub(
        r"\b(?:no[- ]code|without coding|without code)\b",
        "",
        lowered,
    )
    if _contains(title_lowered, _ROBOTICS_MARKERS):
        return "AI robotics"
    if _contains(title_lowered, _MEDIA_MARKERS):
        return "AI video generation"
    if _contains(title_lowered, _AGENT_MARKERS):
        return "Coding agents" if _contains(developer_text, _DEVELOPER_MARKERS) else "AI agents"
    developer_specific = any(product in _DEVELOPER_PRODUCTS for product in products) or any(
        marker in developer_text for marker in (" coding", "codebase", "programming", "github")
    )
    if (
        _contains(developer_text, _DEVELOPER_MARKERS)
        and developer_specific
        and (_AI_ANCHOR.search(text) or products)
    ):
        return "Developer tools"
    for preferred in (
        "Chinese AI models",
        "Open-source AI",
        "AI models",
        "AI productivity",
        "Productivity",
        "Developer tools",
    ):
        if preferred == "Developer tools" and products and not developer_specific:
            continue
        if preferred in entities:
            return preferred
    if products or _AI_ANCHOR.search(text):
        return "AI models"
    return None


def _primary_entity(domain: str, products: tuple[str, ...], title: str) -> str:
    if domain == "AI robotics":
        for product in products:
            if product in {"Figure AI", "Optimus"}:
                return product
        return "AI robotics"
    if domain == "AI video generation":
        media_products = {
            "Sora",
            "Veo",
            "Runway",
            "Kling",
            "Luma",
            "Pika",
            "Higgsfield",
            "Midjourney",
        }
        return next((product for product in products if product in media_products), domain)
    if not products and domain in {
        "AI agents",
        "Coding agents",
        "Developer tools",
        "AI productivity",
        "Productivity",
    }:
        return domain
    for specific in (
        "GPT-4",
        "Gemini",
        "Microsoft 365 Copilot",
        "Claude Code",
        "Claude",
        "ChatGPT",
    ):
        if specific in products:
            if (
                specific == "ChatGPT"
                and "Google AI" in products
                and any(marker in title.lower() for marker in ("war", "panics", "competition"))
            ):
                return "Google AI"
            return specific
    return products[0] if products else "Artificial intelligence"


def _event_type(title: str, domain: str, primary: str) -> str:
    lowered = f" {title.lower()} "
    if any(marker in lowered for marker in (" law", " regulation", " lawsuit", " legal")):
        return "policy_scrutiny"
    if any(
        marker in lowered
        for marker in (" chaos", " board", " leadership", " fired", " resign", " governance")
    ):
        return "governance_change"
    if any(
        marker in lowered
        for marker in (
            " ai war",
            " a.i. war",
            " war is",
            " race for",
            " versus ",
            " vs ",
            " competition",
            " panics",
        )
    ):
        return "competitive_wave"
    if any(
        marker in lowered
        for marker in (
            " introducing ",
            " introduction ",
            " launch",
            " livestream",
            " keynote",
            " devday",
            " revealed",
            " newest",
            " new model",
            " model release",
            " release",
            " is here",
            " event:",
            " ai event",
        )
    ):
        return "release_wave"
    if primary in {"Gemini", "GPT-4", "Microsoft 365 Copilot"} and any(
        marker in lowered for marker in (" hands-on", " multimodal", " evolving", " beyond")
    ):
        return "release_wave"
    if any(
        marker in lowered
        for marker in (
            " problem",
            " scared",
            " disturbing",
            " frightening",
            " warning",
            " sentient",
            " not ready",
            " fake",
            " deepfake",
        )
    ):
        return "risk_debate"
    if any(
        marker in lowered
        for marker in (" benchmark", " compared", " comparison", " tested", " test ")
    ):
        return "benchmark"
    if any(
        marker in lowered
        for marker in (
            " for work",
            " business",
            " company work",
            " productivity",
            " workflow",
            " adoption",
            " recurring",
            " repetitive",
        )
    ):
        return "adoption"
    if any(
        marker in lowered
        for marker in (
            " learns",
            " prove",
            " capable",
            " capability",
            " hands-on",
            " multimodal",
            " reasoning",
        )
    ):
        return "capability_wave"
    if any(marker in lowered for marker in (" made ", " asked ", " using ", " build ", " create")):
        return "practical_use"
    if primary != "Artificial intelligence" or domain != "AI models":
        return "product_update"
    return "broad_subject"


def _context(title: str, domain: str, event_type: str, primary: str) -> str:
    lowered = title.lower()
    if event_type == "competitive_wave" and primary == "Google AI":
        return "Google response to ChatGPT"
    if event_type == "policy_scrutiny":
        return "law and regulation"
    if event_type == "governance_change":
        return "company governance"
    if event_type == "risk_debate":
        if "sentient" in lowered:
            return "sentience claims"
        if "deepfake" in lowered or "fake" in lowered:
            return "synthetic media trust"
        return "reliability and safety"
    if event_type == "release_wave":
        return "new product and capability release"
    if event_type == "benchmark":
        return "comparative performance"
    if event_type == "adoption":
        if "work" in lowered or "business" in lowered or "productivity" in lowered:
            return "workplace adoption"
        return "practical adoption"
    if event_type == "capability_wave":
        if domain == "AI robotics":
            return "robot capability"
        if "multimodal" in lowered:
            return "multimodal capability"
        return "new model capability"
    if event_type == "competitive_wave" and domain == "AI robotics":
        return "robotics capability race"
    if event_type == "competitive_wave":
        return "market competition"
    if event_type == "practical_use":
        return "practical use case"
    return "market activity"


def _claim(event_type: str) -> str:
    return {
        "policy_scrutiny": "face growing legal and regulatory scrutiny",
        "governance_change": "undergo a consequential governance change",
        "competitive_wave": "intensify competitive pressure",
        "release_wave": "introduce a materially new product or capability",
        "risk_debate": "trigger new reliability and safety concerns",
        "benchmark": "show measurable comparative performance",
        "adoption": "move into a concrete adoption context",
        "capability_wave": "demonstrate a newly visible capability",
        "practical_use": "appear in a concrete practical use case",
        "product_update": "show new market activity",
        "broad_subject": "receive renewed attention",
    }[event_type]


def infer_microtopic_identity_v6(document: MicrotopicDocument) -> MicrotopicIdentity | None:
    title = " ".join(document.title.split())
    description = " ".join(document.description[:1_200].split())
    text = f"{title} {description}"
    normalized = tuple(
        dict.fromkeys(
            (*document.entities, *normalize_entities(document.title, document.description))
        )
    )
    products = _detected_products(title, text, normalized)
    domain = _domain(title, text, normalized, products)
    if domain is None:
        return None
    primary = _primary_entity(domain, products, title)
    event_type = _event_type(title, domain, primary)
    context = _context(title, domain, event_type, primary)
    return MicrotopicIdentity(
        domain=domain,
        facet=event_type,
        primary_entity=primary,
        secondary_entities=tuple(
            entity for entity in dict.fromkeys((*products, *normalized)) if entity != primary
        ),
        audience=_audience(text),
        user_problem=context,
        core_claim=_claim(event_type),
        workflow_context=context,
        content_format=_content_format(text),
    )


def _label(identity: MicrotopicIdentity) -> str:
    entity = identity.primary_entity
    context = identity.workflow_context
    if identity.facet == "competitive_wave" and context == "Google response to ChatGPT":
        return "Google–ChatGPT competitive response"
    if identity.facet == "competitive_wave" and identity.domain == "AI robotics":
        return "AI robotics capability race"
    suffix = {
        "policy_scrutiny": "legal and regulatory scrutiny",
        "governance_change": "governance change",
        "competitive_wave": "competitive pressure",
        "release_wave": "product and capability release",
        "risk_debate": f"{context} concerns",
        "benchmark": "comparative performance",
        "adoption": context,
        "capability_wave": context,
        "practical_use": "practical use cases",
        "product_update": "market activity",
        "broad_subject": "renewed attention",
    }[identity.facet]
    return f"{entity} {suffix}"


def _specificity(identity: MicrotopicIdentity, *, document_count: int) -> float:
    named_product = identity.primary_entity not in {
        "Artificial intelligence",
        "AI agents",
        "AI robotics",
        "AI video generation",
        "AI productivity",
        "Coding agents",
        "Developer tools",
        "Productivity",
    }
    specific_event = identity.facet not in {"broad_subject", "product_update"}
    specific_context = identity.workflow_context not in {"market activity", "practical use case"}
    score = 40.0
    score += 20 if named_product else 8
    score += 15 if specific_event else 0
    score += 10 if specific_context else 0
    score += min(10, document_count * 2)
    return round(min(100.0, score), 1)


def cluster_microtopics_v6(documents: list[MicrotopicDocument]) -> list[MicrotopicCluster]:
    identities: dict[str, MicrotopicIdentity] = {}
    grouped: defaultdict[tuple[str, ...], list[MicrotopicDocument]] = defaultdict(list)
    for document in documents:
        identity = infer_microtopic_identity_v6(document)
        if identity is None:
            continue
        identities[document.id] = identity
        # Trend identity intentionally excludes content format, hook, audience and
        # creator angle. Those belong to strategy, not to the observed event.
        grouped[
            (
                identity.domain,
                identity.primary_entity,
                identity.facet,
                identity.workflow_context,
            )
        ].append(document)

    clusters: list[MicrotopicCluster] = []
    for group_key, members in grouped.items():
        identity = identities[members[0].id]
        formats = Counter(identities[member.id].content_format for member in members)
        specificity = _specificity(identity, document_count=len(members))
        reasons: list[str] = []
        if identity.facet == "broad_subject":
            reasons.append("broad_subject_without_event")
        if (
            identity.facet == "release_wave"
            and identity.primary_entity == "Artificial intelligence"
        ):
            reasons.append("unnamed_release_without_product_anchor")
        if specificity < 70:
            reasons.append("specificity_below_visible_floor")
        label = _label(identity)
        fingerprint = "|".join(value.lower() for value in group_key)
        key = f"micro-v6-{sha256(fingerprint.encode()).hexdigest()[:18]}"
        secondary = tuple(
            dict.fromkeys(
                entity
                for member in members
                for entity in identities[member.id].secondary_entities
                if entity != identity.primary_entity
            )
        )
        clusters.append(
            MicrotopicCluster(
                key=key,
                label=label,
                aliases=(label, f"{identity.primary_entity} {identity.workflow_context}"),
                entities=tuple(
                    dict.fromkeys((identity.primary_entity, *secondary, identity.domain))
                ),
                document_ids=tuple(dict.fromkeys(member.id for member in members)),
                specificity_score=specificity,
                facet=identity.facet,
                domain=identity.domain,
                primary_entity=identity.primary_entity,
                secondary_entities=secondary,
                audience=identity.audience,
                user_problem=identity.user_problem,
                core_claim=identity.core_claim,
                workflow_context=identity.workflow_context,
                format_distribution=tuple(
                    (name, round(count / len(members), 3)) for name, count in formats.most_common()
                ),
                thesis=(
                    f"Stored evidence shows {label.lower()}; the identity is based on the "
                    f"subject and event shared by {len(members)} videos, not their format."
                ),
                thesis_support_ratio=1.0,
                visible=not reasons,
                reason_codes=tuple(reasons or ("subject_event_identity_supported",)),
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


__all__ = [
    "MICROTOPIC_V6_VERSION",
    "cluster_microtopics_v6",
    "infer_microtopic_identity_v6",
]
