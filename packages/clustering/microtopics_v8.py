from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from hashlib import sha256

from packages.clustering.microtopics import (
    MicrotopicCluster,
    MicrotopicDocument,
    MicrotopicIdentity,
    _audience,
    _content_format,
)
from packages.clustering.microtopics_v7 import normalize_format_neutral_title

MICROTOPIC_V8_VERSION = "microtopic-clustering-v8-concrete-claim"


@dataclass(frozen=True)
class _AnchorDefinition:
    label: str
    pattern: re.Pattern[str]
    version_group: str | None = None


@dataclass(frozen=True)
class _ConceptDefinition:
    key: str
    label: str
    pattern: re.Pattern[str]


def _pattern(value: str) -> re.Pattern[str]:
    return re.compile(value, re.IGNORECASE)


_ANCHORS: tuple[_AnchorDefinition, ...] = (
    _AnchorDefinition("Microsoft 365 Copilot", _pattern(r"\bmicrosoft (?:365|m365) copilot\b")),
    _AnchorDefinition("GitHub Copilot", _pattern(r"\bgithub copilot\b")),
    _AnchorDefinition("Claude Code", _pattern(r"\bclaude code\b")),
    _AnchorDefinition("OpenAI Codex", _pattern(r"\b(?:openai )?codex\b")),
    _AnchorDefinition("NotebookLM", _pattern(r"\bnotebook\s*lm\b")),
    _AnchorDefinition("Stable Diffusion", _pattern(r"\bstable diffusion\b")),
    _AnchorDefinition("ComfyUI", _pattern(r"\bcomfy\s*ui\b")),
    _AnchorDefinition("Higgsfield", _pattern(r"\bhiggsfield\b")),
    _AnchorDefinition("Midjourney", _pattern(r"\bmidjourney\b")),
    _AnchorDefinition("Adobe Firefly", _pattern(r"\b(?:adobe )?firefly\b")),
    _AnchorDefinition("LangChain", _pattern(r"\blangchain\b")),
    _AnchorDefinition("OpenClaw", _pattern(r"\bopenclaw\b")),
    _AnchorDefinition("ChatGPT", _pattern(r"\bchatgpt\b")),
    _AnchorDefinition("OpenAI", _pattern(r"\bopenai\b")),
    _AnchorDefinition("Anthropic", _pattern(r"\banthropic\b")),
    _AnchorDefinition("Cursor", _pattern(r"\bcursor\b")),
    _AnchorDefinition("Windsurf", _pattern(r"\bwindsurf\b")),
    _AnchorDefinition("Lovable", _pattern(r"\blovable\b")),
    _AnchorDefinition("Ollama", _pattern(r"\bollama\b")),
    _AnchorDefinition("n8n", _pattern(r"\bn8n\b")),
    _AnchorDefinition("Manus", _pattern(r"\bmanus\b")),
    _AnchorDefinition("Hermes", _pattern(r"\bhermes\b")),
    _AnchorDefinition("Figma", _pattern(r"\bfigma\b")),
    _AnchorDefinition("Canva", _pattern(r"\bcanva\b")),
    _AnchorDefinition("Sora", _pattern(r"\bsora(?:\s+(?P<version>\d+(?:\.\d+)?))?\b"), "version"),
    _AnchorDefinition("Veo", _pattern(r"\bveo(?:\s+(?P<version>\d+(?:\.\d+)?))?\b"), "version"),
    _AnchorDefinition("Kling", _pattern(r"\bkling(?:\s+(?P<version>\d+(?:\.\d+)?))?\b"), "version"),
    _AnchorDefinition(
        "Runway", _pattern(r"\brunway(?:\s+(?P<version>\d+(?:\.\d+)?))?\b"), "version"
    ),
    _AnchorDefinition(
        "Seedance", _pattern(r"\bseedance(?:\s+(?P<version>\d+(?:\.\d+)?))?\b"), "version"
    ),
    _AnchorDefinition("Flux", _pattern(r"\bflux(?:\s+(?P<version>\d+(?:\.\d+)?))?\b"), "version"),
    _AnchorDefinition("Luma", _pattern(r"\bluma(?:\s+(?P<version>\d+(?:\.\d+)?))?\b"), "version"),
    _AnchorDefinition("Pika", _pattern(r"\bpika(?:\s+(?P<version>\d+(?:\.\d+)?))?\b"), "version"),
    _AnchorDefinition(
        "DeepSeek",
        _pattern(
            r"\bdeepseek(?:[- ]+(?P<version>(?:v|r)?\d+(?:\.\d+)?(?:[- ]?(?:pro|flash))?))?\b"
        ),
        "version",
    ),
    _AnchorDefinition(
        "Qwen",
        _pattern(r"\bqwen(?:[- ]?(?P<version>\d+(?:\.\d+)?(?:[- ]?(?:max|coder|vl))?))?\b"),
        "version",
    ),
    _AnchorDefinition(
        "Kimi", _pattern(r"\bkimi(?:[- ]?(?P<version>k?\d+(?:\.\d+)?))?\b"), "version"
    ),
    _AnchorDefinition(
        "MiniMax", _pattern(r"\bminimax(?:[- ]?(?P<version>[a-z]?\d+(?:\.\d+)?))?\b"), "version"
    ),
    _AnchorDefinition("GLM", _pattern(r"\bglm(?:[- ]?(?P<version>\d+(?:\.\d+)?))?\b"), "version"),
    _AnchorDefinition(
        "Llama", _pattern(r"\bllama(?:[- ]?(?P<version>\d+(?:\.\d+)?))?\b"), "version"
    ),
    _AnchorDefinition(
        "Mistral", _pattern(r"\bmistral(?:\s+(?P<version>\w+(?:\s+\d+(?:\.\d+)?)?))?\b"), "version"
    ),
    _AnchorDefinition(
        "Gemma", _pattern(r"\bgemma(?:[- ]?(?P<version>\d+(?:\.\d+)?))?\b"), "version"
    ),
    _AnchorDefinition("Grok", _pattern(r"\bgrok(?:[- ]?(?P<version>\d+(?:\.\d+)?))?\b"), "version"),
    _AnchorDefinition(
        "GPT", _pattern(r"\bgpt[- ]?(?P<version>[3-9](?:\.\d+)?(?:[a-z])?)\b"), "version"
    ),
    _AnchorDefinition(
        "Claude",
        _pattern(r"\bclaude(?:\s+(?P<version>(?:opus|sonnet|haiku)(?:\s+\d+(?:\.\d+)?)?))?\b"),
        "version",
    ),
    _AnchorDefinition(
        "Gemini",
        _pattern(r"\bgemini(?:\s+(?P<version>\d+(?:\.\d+)?(?:\s+(?:pro|flash|ultra))?))?\b"),
        "version",
    ),
)

_CONCEPTS: tuple[_ConceptDefinition, ...] = (
    _ConceptDefinition(
        "consistent_characters",
        "consistent characters",
        _pattern(r"\b(?:consistent|same) (?:ai )?characters?\b|\bcharacter consistency\b"),
    ),
    _ConceptDefinition(
        "context_window",
        "long context and context windows",
        _pattern(r"\bcontext window\b|\bmillion[- ]token context\b|\blong context\b"),
    ),
    _ConceptDefinition(
        "memory_context",
        "memory and persistent context",
        _pattern(r"\bmemor(?:y|ies)\b|\bpersistent context\b"),
    ),
    _ConceptDefinition(
        "skills_plugins",
        "skills and plugins",
        _pattern(r"\bskills?\b|\bplugins?\b|\bextensions?\b"),
    ),
    _ConceptDefinition(
        "mcp_integrations", "MCP integrations", _pattern(r"\bmodel context protocol\b|\bmcp\b")
    ),
    _ConceptDefinition(
        "token_cost",
        "token use and context cost",
        _pattern(r"\btokens?\b|\bcontext cost\b|\beating your tokens\b"),
    ),
    _ConceptDefinition(
        "price_cost",
        "price and inference cost",
        _pattern(
            r"\bpric(?:e|es|ing)\b|\bcheaper\b|\bcosts?\b|\bdiscount\b|"
            r"\bfree tier\b|\bsubscription\b"
        ),
    ),
    _ConceptDefinition(
        "local_inference",
        "local and on-device inference",
        _pattern(r"\blocal(?:ly)?\b|\bon[- ]device\b|\bself[- ]host(?:ed|ing)?\b|\boffline\b"),
    ),
    _ConceptDefinition(
        "open_source",
        "open weights and open source",
        _pattern(r"\bopen[- ]source\b|\bopen weights?\b"),
    ),
    _ConceptDefinition(
        "voice_mode",
        "voice interaction",
        _pattern(r"\bvoice (?:mode|assistant|interaction|dictation)\b|\breal[- ]time voice\b"),
    ),
    _ConceptDefinition(
        "browser_use",
        "browser control and web use",
        _pattern(r"\bbrowser\b|\bcomputer use\b|\bweb navigation\b"),
    ),
    _ConceptDefinition(
        "agent_autonomy",
        "agent autonomy and orchestration",
        _pattern(
            r"\bautonomous\b|\bmulti[- ]agent\b|\bagent orchestration\b|\bsubagents?\b|\bagentic\b"
        ),
    ),
    _ConceptDefinition(
        "coding_work",
        "software development work",
        _pattern(
            r"\bcoding\b|\bcodebase\b|\bprogramming\b|\bsoftware development\b|\bvibe coding\b"
        ),
    ),
    _ConceptDefinition(
        "website_building",
        "website generation",
        _pattern(r"\bwebsites?\b|\blanding pages?\b|\bwordpress\b"),
    ),
    _ConceptDefinition(
        "app_building",
        "application generation",
        _pattern(r"\bbuild(?:ing)? (?:an? )?apps?\b|\bapp builder\b|\bmobile apps?\b|\bsaas\b"),
    ),
    _ConceptDefinition(
        "business_operations",
        "business operations",
        _pattern(
            r"\bbusiness operations?\b|\bback office\b|\bclient deliverables?\b|"
            r"\bsolo business\b|\bone[- ]person business\b"
        ),
    ),
    _ConceptDefinition(
        "workflow_automation",
        "workflow automation",
        _pattern(r"\bworkflows?\b|\bautomation\b|\bautomate\b|\brecurring tasks?\b"),
    ),
    _ConceptDefinition(
        "content_repurposing",
        "content repurposing",
        _pattern(r"\brepurpose\b|\bcontent system\b|\bcontent pipeline\b"),
    ),
    _ConceptDefinition(
        "lead_generation",
        "lead generation",
        _pattern(r"\bleads?\b|\blead generation\b|\bprospecting\b"),
    ),
    _ConceptDefinition(
        "video_generation",
        "AI video generation",
        _pattern(
            r"\bai (?:video|film|movie)\b|\bvideo generat(?:ion|or)\b|"
            r"\btext[- ]to[- ]video\b|\bimage[- ]to[- ]video\b"
        ),
    ),
    _ConceptDefinition(
        "image_generation",
        "AI image generation",
        _pattern(r"\bai images?\b|\bimage generat(?:ion|or)\b|\btext[- ]to[- ]image\b"),
    ),
    _ConceptDefinition(
        "avatar_lipsync",
        "avatars and lip sync",
        _pattern(r"\bavatars?\b|\blip[- ]?sync\b|\btalking (?:head|avatar)\b"),
    ),
    _ConceptDefinition(
        "film_production",
        "AI filmmaking",
        _pattern(r"\bfilmmak(?:ing|ers?)\b|\bshort films?\b|\bmovies?\b|\bstoryboards?\b"),
    ),
    _ConceptDefinition(
        "music_audio",
        "music and audio generation",
        _pattern(r"\bmusic generat(?:ion|or)\b|\bai music\b|\bsongs?\b|\baudio generation\b"),
    ),
    _ConceptDefinition(
        "research_science",
        "research and scientific discovery",
        _pattern(r"\bresearch\b|\bscientific discovery\b|\bdrug discovery\b|\bpapers?\b"),
    ),
    _ConceptDefinition(
        "security_privacy",
        "security and privacy",
        _pattern(r"\bsecurity\b|\bprivacy\b|\bcyber(?:security)?\b|\bdata leak\b|\bjailbreak\b"),
    ),
    _ConceptDefinition(
        "legal_copyright",
        "copyright and legal disputes",
        _pattern(r"\bcopyright\b|\blawsuits?\b|\blegal\b|\bregulation\b"),
    ),
    _ConceptDefinition(
        "education",
        "education and learning",
        _pattern(r"\beducation\b|\bstudents?\b|\bstudying\b|\bschools?\b|\bteachers?\b"),
    ),
    _ConceptDefinition(
        "healthcare",
        "healthcare use",
        _pattern(r"\bhealthcare\b|\bmedical\b|\bclinical\b|\bpatients?\b"),
    ),
    _ConceptDefinition(
        "finance_trading",
        "finance and trading",
        _pattern(r"\bfinance\b|\btrading\b|\bstocks?\b|\bcrypto\b|\binvesting\b"),
    ),
    _ConceptDefinition(
        "enterprise_adoption",
        "enterprise adoption",
        _pattern(
            r"\benterprise\b|\bworkplace adoption\b|\bcompany adoption\b|\bproduction readiness\b"
        ),
    ),
    _ConceptDefinition(
        "hardware_compute",
        "hardware and inference compute",
        _pattern(r"\bgpus?\b|\bvram\b|\bcompute\b|\bchips?\b|\baccelerators?\b"),
    ),
    _ConceptDefinition(
        "robotics", "robot capabilities", _pattern(r"\brobots?\b|\brobotics\b|\bhumanoid\b")
    ),
    _ConceptDefinition(
        "benchmark",
        "measured performance",
        _pattern(r"\bbenchmarks?\b|\bperformance\b|\baccuracy\b|\blatency\b|\bstress test\b"),
    ),
    _ConceptDefinition(
        "release",
        "release and capability rollout",
        _pattern(
            r"\breleas(?:e|ed)\b|\blaunched?\b|\bintroducing\b|\bunveil(?:ed)?\b|"
            r"\bis here\b|\bnew version\b|\bupgrade\b|\bupdate\b"
        ),
    ),
)

_COMPARISON = _pattern(r"\b(?:vs\.?|versus|compared?|comparison|better than|beats?)\b")
_AI_CONTEXT = _pattern(r"\b(?:ai|artificial intelligence|llm|model|agent|coding|chatbot)\b")

_PARENT_ANCHORS: dict[str, frozenset[str]] = {
    "OpenAI": frozenset({"ChatGPT", "GPT", "OpenAI Codex"}),
    "Anthropic": frozenset({"Claude", "Claude Code"}),
}

_TAUTOLOGICAL_DOMAIN_CONCEPTS = {
    ("AI agents", "agent_autonomy"),
    ("AI coding", "coding_work"),
    ("AI image generation", "image_generation"),
    ("AI robotics", "robotics"),
    ("AI video generation", "video_generation"),
    ("Local AI", "local_inference"),
}


def _normalize_version(value: str) -> str:
    compact = " ".join(value.replace("-", " ").split())
    parts = compact.split()
    normalized: list[str] = []
    for part in parts:
        lowered = part.lower()
        if re.fullmatch(r"\d+(?:\.\d+)?", lowered):
            number_parts = lowered.split(".")
            while len(number_parts) > 1 and number_parts[-1] == "0":
                number_parts.pop()
            normalized.append(".".join(number_parts))
        elif re.fullmatch(r"[vr]\d+(?:\.\d+)?", lowered):
            normalized.append(f"{lowered[0].upper()}{_normalize_version(lowered[1:])}")
        else:
            normalized.append(part.upper() if lowered in {"vl", "glm"} else part.title())
    return " ".join(normalized)


def _anchors(title: str) -> tuple[str, ...]:
    found: list[str] = []
    for definition in _ANCHORS:
        match = definition.pattern.search(title)
        if not match:
            continue
        if definition.label in {"Gemini", "Claude"} and definition.version_group:
            version = match.groupdict().get(definition.version_group)
            if not version and not _AI_CONTEXT.search(title):
                continue
        label = definition.label
        if definition.version_group and (
            version := match.groupdict().get(definition.version_group)
        ):
            label = f"{label} {_normalize_version(version)}"
        if label not in found:
            found.append(label)

    bases = {label.split()[0] if label.startswith("GPT ") else label for label in found}
    filtered: list[str] = []
    for label in found:
        children = _PARENT_ANCHORS.get(label)
        if children and any(
            child in bases or any(candidate.startswith(f"{child} ") for candidate in found)
            for child in children
        ):
            continue
        if label == "Claude" and "Claude Code" in found:
            continue
        filtered.append(label)
    return tuple(filtered)


def _domain_anchor(title: str) -> str | None:
    lowered = title.lower()
    if re.search(
        r"\bai (?:video|film|movie)\b|\bvideo generat(?:ion|or)\b|"
        r"\bai characters?\b.*\b(?:video|scene)\b",
        lowered,
    ):
        return "AI video generation"
    if re.search(r"\b(?:ai|coding) agents?\b|\bagentic\b", lowered):
        return "AI agents"
    if re.search(r"\blocal ai\b|\blocal llms?\b", lowered):
        return "Local AI"
    if re.search(r"\bai coding\b|\bcoding assistants?\b", lowered):
        return "AI coding"
    if re.search(r"\bai images?\b|\bimage generat(?:ion|or)\b", lowered):
        return "AI image generation"
    if re.search(r"\bai robotics?\b|\bhumanoid robots?\b", lowered):
        return "AI robotics"
    return None


def _concept(title: str) -> _ConceptDefinition | None:
    return next((concept for concept in _CONCEPTS if concept.pattern.search(title)), None)


def infer_microtopic_identity_v8(document: MicrotopicDocument) -> MicrotopicIdentity | None:
    clean_title = normalize_format_neutral_title(document.title)
    anchors = _anchors(clean_title)
    concept = _concept(clean_title)

    if len(anchors) >= 2 and _COMPARISON.search(clean_title):
        pair = tuple(sorted(anchors[:2], key=str.casefold))
        primary = " / ".join(pair)
        facet = "product_comparison"
        concept_label = "measured product difference"
        secondary = pair
    else:
        primary = anchors[0] if anchors else _domain_anchor(clean_title) or ""
        if not primary or concept is None:
            return None
        if not anchors and (primary, concept.key) in _TAUTOLOGICAL_DOMAIN_CONCEPTS:
            return None
        facet = concept.key
        concept_label = concept.label
        secondary = anchors[1:]

    return MicrotopicIdentity(
        domain=_domain_anchor(clean_title) or "AI products and research",
        facet=facet,
        primary_entity=primary,
        secondary_entities=tuple(secondary),
        audience=_audience(f"{clean_title} {document.description[:1_200]}"),
        user_problem=concept_label,
        core_claim=f"evidence concerns {concept_label}",
        workflow_context=concept_label,
        content_format=_content_format(document.title),
    )


def topic_key_v8(identity: MicrotopicIdentity) -> str:
    fingerprint = "|".join(
        (identity.primary_entity.casefold(), identity.facet, identity.workflow_context.casefold())
    )
    return f"micro-v8-{sha256(fingerprint.encode()).hexdigest()[:18]}"


def _label(identity: MicrotopicIdentity) -> str:
    return f"{identity.primary_entity} — {identity.workflow_context}"


def cluster_microtopics_v8(documents: list[MicrotopicDocument]) -> list[MicrotopicCluster]:
    identities: dict[str, MicrotopicIdentity] = {}
    grouped: defaultdict[str, list[MicrotopicDocument]] = defaultdict(list)
    for document in documents:
        identity = infer_microtopic_identity_v8(document)
        if identity is None:
            continue
        identities[document.id] = identity
        grouped[topic_key_v8(identity)].append(document)

    clusters: list[MicrotopicCluster] = []
    for key, members in grouped.items():
        identity = identities[members[0].id]
        label = _label(identity)
        formats = Counter(identities[member.id].content_format for member in members)
        named = identity.domain == "AI products and research"
        specificity = min(100.0, (82 if named else 72) + min(len(members), 6) * 2)
        clusters.append(
            MicrotopicCluster(
                key=key,
                label=label,
                aliases=(label,),
                entities=tuple(
                    dict.fromkeys(
                        (identity.primary_entity, *identity.secondary_entities, identity.domain)
                    )
                ),
                document_ids=tuple(dict.fromkeys(member.id for member in members)),
                specificity_score=round(specificity, 1),
                facet=identity.facet,
                domain=identity.domain,
                primary_entity=identity.primary_entity,
                secondary_entities=identity.secondary_entities,
                audience=identity.audience,
                user_problem=identity.user_problem,
                core_claim=identity.core_claim,
                workflow_context=identity.workflow_context,
                format_distribution=tuple(
                    (name, round(count / len(members), 3)) for name, count in formats.most_common()
                ),
                thesis=(
                    f"Stored titles independently connect {identity.primary_entity} with "
                    f"{identity.workflow_context}; presentation format is excluded from the key."
                ),
                thesis_support_ratio=1.0,
                visible=True,
                reason_codes=("named_entity_and_concrete_claim_supported",),
            )
        )
    return sorted(
        clusters,
        key=lambda cluster: (-len(cluster.document_ids), -cluster.specificity_score, cluster.label),
    )


__all__ = [
    "MICROTOPIC_V8_VERSION",
    "cluster_microtopics_v8",
    "infer_microtopic_identity_v8",
    "topic_key_v8",
]
