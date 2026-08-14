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

MICROTOPIC_V7_VERSION = "microtopic-clustering-v7.1-format-neutral-historical-ai"

_FORMAT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"(?i)\b(?:tutorial|guide|review|explained|demo|livestream|live stream|"
        r"podcast|shorts?|reaction|lecture|course|lesson|interview|keynote|"
        r"documentary|beginners?|advanced|walkthrough|hands[- ]on)\b"
    ),
    re.compile(r"(?i)\bpart\s+\d+\b"),
    re.compile(r"(?i)\b(?:full|complete)\s+(?:course|guide|tutorial)\b"),
    re.compile(r"(?i)\bin\s+\d+\s+(?:minutes?|mins?|hours?)\b"),
)

_SUBJECT_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Microsoft 365 Copilot", (r"\bmicrosoft 365 copilot\b", r"\bmicrosoft copilot\b")),
    ("Claude Code", (r"\bclaude code\b",)),
    ("Stable Diffusion", (r"\bstable diffusion\b",)),
    ("Google Duplex", (r"\bgoogle duplex\b",)),
    ("TensorFlow.js", (r"\btensorflow\.?js\b",)),
    ("Reinforcement learning", (r"\breinforcement learning\b", r"\bq[- ]learning\b")),
    (
        "Generative adversarial networks",
        (r"\bgenerative adversarial networks?\b", r"\bGANs?\b"),
    ),
    (
        "Natural language processing",
        (r"\bnatural language processing\b", r"\bNLP\b"),
    ),
    ("Computer vision", (r"\bcomputer vision\b",)),
    ("Neural networks", (r"\bneural networks?\b",)),
    ("Machine learning", (r"\bmachine learning\b",)),
    ("Deep learning", (r"\bdeep learning\b",)),
    ("Artificial intelligence", (r"\bartificial intelligence\b", r"\bA\.?I\.?\b")),
    ("TensorFlow", (r"\btensorflow\b",)),
    ("PyTorch", (r"\bpytorch\b",)),
    ("Keras", (r"\bkeras\b",)),
    ("OpenAI Gym", (r"\bopenai gym\b",)),
    ("OpenAI", (r"\bopenai\b",)),
    ("DeepMind", (r"\bdeepmind\b",)),
    ("AlphaGo", (r"\balphago\b",)),
    ("IBM Watson", (r"\bibm watson\b",)),
    ("BERT", (r"\bBERT\b",)),
    ("GPT-2", (r"\bgpt[- ]?2\b",)),
    ("GPT-3", (r"\bgpt[- ]?3\b",)),
    ("GPT-4", (r"\bgpt[- ]?4\b",)),
    ("ChatGPT", (r"\bchatgpt\b",)),
    (
        "Gemini",
        (
            r"\bgoogle gemini\b",
            r"\bgemini\s+(?:ai|llm|model|chatbot|assistant)\b",
        ),
    ),
    (
        "Claude",
        (
            r"\banthropic claude\b",
            r"\bclaude\s+(?:ai|llm|model|chatbot|assistant)\b",
        ),
    ),
    ("DeepSeek", (r"\bdeepseek\b",)),
    ("Midjourney", (r"\bmidjourney\b",)),
    ("AI robotics", (r"\bAI\s+robotics?\b", r"\brobotics?\s+AI\b")),
    (
        "Autonomous driving AI",
        (
            r"\bself[- ]driving\s+(?:cars?\s+)?AI\b",
            r"\bautonomous driving\s+AI\b",
        ),
    ),
    ("AI ethics", (r"\bAI\s+ethics\b", r"\bethics\s+of\s+AI\b")),
    ("AI chatbots", (r"\bAI\s+chatbots?\b", r"\bchatbots?\s+AI\b")),
    (
        "AI face recognition",
        (r"\bAI\s+face recognition\b", r"\bface recognition\s+AI\b"),
    ),
)

_DOMAIN_BY_SUBJECT = {
    "AI robotics": "AI robotics",
    "Autonomous driving AI": "AI robotics",
    "Stable Diffusion": "AI media generation",
    "Midjourney": "AI media generation",
    "AI ethics": "AI safety and ethics",
    "AI face recognition": "AI safety and ethics",
    "TensorFlow.js": "AI developer tools",
    "TensorFlow": "AI developer tools",
    "PyTorch": "AI developer tools",
    "Keras": "AI developer tools",
    "OpenAI Gym": "AI developer tools",
    "BERT": "AI models and research",
    "GPT-2": "AI models and research",
    "GPT-3": "AI models and research",
    "GPT-4": "AI models and research",
    "Machine learning": "AI models and research",
    "Deep learning": "AI models and research",
    "Neural networks": "AI models and research",
    "Reinforcement learning": "AI models and research",
    "Generative adversarial networks": "AI models and research",
    "Natural language processing": "AI models and research",
    "Computer vision": "AI models and research",
}

_GENERIC_SUBJECTS = {
    "Artificial intelligence",
    "Machine learning",
    "Deep learning",
    "Neural networks",
}

_DOMAIN_SUBJECTS = {
    *_GENERIC_SUBJECTS,
    "Reinforcement learning",
    "Generative adversarial networks",
    "Natural language processing",
    "Computer vision",
    "AI robotics",
    "Autonomous driving AI",
    "AI ethics",
    "AI chatbots",
    "AI face recognition",
}

_SUBJECT_PRIORITY = {
    subject: index
    for index, subject in enumerate(
        (
            "Microsoft 365 Copilot",
            "Claude Code",
            "Stable Diffusion",
            "Google Duplex",
            "TensorFlow.js",
            "OpenAI Gym",
            "IBM Watson",
            "TensorFlow",
            "PyTorch",
            "Keras",
            "AlphaGo",
            "BERT",
            "GPT-2",
            "GPT-3",
            "GPT-4",
            "ChatGPT",
            "Gemini",
            "Claude",
            "DeepSeek",
            "Midjourney",
            "OpenAI",
            "DeepMind",
            "AI robotics",
            "Autonomous driving AI",
            "AI ethics",
            "AI chatbots",
            "AI face recognition",
            "Reinforcement learning",
            "Generative adversarial networks",
            "Natural language processing",
            "Computer vision",
            "Neural networks",
            "Machine learning",
            "Deep learning",
            "Artificial intelligence",
        )
    )
}

_TECHNICAL_CONTEXT_PATTERN = re.compile(
    r"(?i)\b(?:ai|artificial intelligence|machine learning|deep learning|neural|"
    r"network|model|training|python|tensorflow|pytorch|transformer|language|"
    r"classification|regression|computer vision|data science|algorithm|research)\b"
)

_VERSIONABLE_SUBJECTS = {
    "TensorFlow",
    "TensorFlow.js",
    "PyTorch",
    "Keras",
}


def normalize_format_neutral_title(title: str) -> str:
    """Remove presentation choices while preserving the substantive subject."""

    value = re.sub(r"(?i)\bfor\s+(?:beginners?|advanced users?)\b", " ", title)
    for pattern in _FORMAT_PATTERNS:
        value = pattern.sub(" ", value)
    value = re.sub(r"[|:–—\[\](){}]+", " ", value)
    value = re.sub(r"\s+", " ", value).strip(" -.,")
    return value


def _ambiguous_subject_has_technical_context(subject: str, title: str) -> bool:
    """Reject common-word/acronym collisions seen in the training partition.

    These checks deliberately use only title semantics, never future performance.
    They prevent astrology ``Gemini``, personal-name ``Claude``/``Bert``, Indonesian
    ``keras`` ("hard"), Bengali ``gan`` ("song"), and neuro-linguistic ``NLP``
    videos from becoming AI evidence.
    """

    if subject == "Generative adversarial networks":
        return bool(
            re.search(r"(?i)\bgenerative adversarial networks?\b", title)
            or (re.search(r"\bGANs?\b", title) and _TECHNICAL_CONTEXT_PATTERN.search(title))
        )
    if subject == "Keras":
        return bool(_TECHNICAL_CONTEXT_PATTERN.search(title))
    if subject == "BERT":
        return bool(re.search(r"\bBERT\b", title) and _TECHNICAL_CONTEXT_PATTERN.search(title))
    if subject == "Natural language processing":
        return bool(
            re.search(r"(?i)\bnatural language processing\b", title)
            or (re.search(r"\bNLP\b", title) and _TECHNICAL_CONTEXT_PATTERN.search(title))
        )
    if subject == "DeepMind":
        return bool(
            re.search(
                r"(?i)\b(?:google|ai|artificial intelligence|machine learning|"
                r"deep learning|neural|alphago|health|research|starcraft|pysc2)\b",
                title,
            )
        )
    if subject == "Artificial intelligence":
        explicit = re.search(r"(?i)\bartificial intelligence\b|\bA\.I\.\b", title)
        abbreviated = re.search(r"\bAI\b", title)
        if explicit:
            return True
        if not abbreviated or not _TECHNICAL_CONTEXT_PATTERN.search(title):
            return False
        return not re.search(
            r"(?i)\b(?:gameplay|career mode|let'?s play|npc|versus ai|vs ai|ai battle)\b",
            title,
        )
    return True


def _subjects(title: str) -> tuple[str, ...]:
    matches: list[str] = []
    for canonical, patterns in _SUBJECT_PATTERNS:
        if any(re.search(pattern, title, flags=re.IGNORECASE) for pattern in patterns) and (
            _ambiguous_subject_has_technical_context(canonical, title)
        ):
            matches.append(canonical)
    # Prefer a concrete product, model or specialized technique over a parent
    # domain anchor, independent of regex declaration order.
    return tuple(
        sorted(
            dict.fromkeys(matches),
            key=lambda subject: (_SUBJECT_PRIORITY.get(subject, 10_000), subject),
        )
    )


def _versioned_subject(subject: str, clean_title: str) -> str:
    if (
        subject not in _VERSIONABLE_SUBJECTS
        or subject in _DOMAIN_SUBJECTS
        or any(character.isdigit() for character in subject)
    ):
        return subject
    pattern = re.compile(
        rf"(?i)\b{re.escape(subject)}\s+(?:v(?:ersion)?\s*)?(\d+(?:\.\d+){{0,2}})\b"
    )
    match = pattern.search(clean_title)
    if not match:
        return subject
    parts = match.group(1).split(".")
    while len(parts) > 1 and parts[-1] == "0":
        parts.pop()
    return f"{subject} {'.'.join(parts)}"


def _facet(clean_title: str) -> str:
    lowered = f" {clean_title.lower()} "
    if any(
        marker in lowered
        for marker in (
            " ethics",
            " bias",
            " safety",
            " dangerous",
            " risk",
            " privacy",
            " surveillance",
            " discrimination",
            " threat",
        )
    ):
        return "safety_ethics"
    if any(
        marker in lowered
        for marker in (
            " released",
            " release",
            " introducing",
            " launches",
            " launched",
            " announcement",
            " announces",
            " unveiled",
            " is here",
            " new version",
        )
    ):
        return "release_wave"
    if any(
        marker in lowered
        for marker in (
            " benchmark",
            " comparison",
            " compared",
            " versus ",
            " vs ",
            " performance",
            " faster",
            " accuracy",
        )
    ):
        return "benchmark"
    if any(
        marker in lowered
        for marker in (
            " breakthrough",
            " beats ",
            " learns",
            " achieves",
            " can now",
            " capability",
            " state of the art",
            " state-of-the-art",
        )
    ):
        return "capability_wave"
    if any(
        marker in lowered
        for marker in (
            " research",
            " paper",
            " study",
            " architecture",
            " method",
            " discovery",
        )
    ):
        return "research_result"
    if any(
        marker in lowered
        for marker in (
            " business",
            " healthcare",
            " medical",
            " finance",
            " education",
            " industry",
            " workplace",
            " adoption",
            " production",
        )
    ):
        return "adoption"
    if any(
        marker in lowered
        for marker in (
            " build ",
            " create ",
            " train ",
            " classify",
            " detect",
            " implement",
            " using ",
            " with python",
        )
    ):
        return "practical_use"
    return "market_activity"


def _context(facet: str) -> str:
    return {
        "safety_ethics": "safety and ethics",
        "release_wave": "product or research release",
        "benchmark": "comparative performance",
        "capability_wave": "newly demonstrated capability",
        "research_result": "research result",
        "adoption": "domain adoption",
        "practical_use": "practical implementation",
        "market_activity": "market and creator activity",
    }[facet]


def _claim(facet: str) -> str:
    return {
        "safety_ethics": "raise a concrete safety or ethics question",
        "release_wave": "introduce a materially new release",
        "benchmark": "show comparative performance",
        "capability_wave": "demonstrate a newly visible capability",
        "research_result": "present a new research result",
        "adoption": "move into a concrete adoption domain",
        "practical_use": "appear in a concrete implementation",
        "market_activity": "receive renewed creator attention",
    }[facet]


def infer_microtopic_identity_v7(document: MicrotopicDocument) -> MicrotopicIdentity | None:
    clean_title = normalize_format_neutral_title(document.title)
    subjects = _subjects(clean_title)
    if not subjects:
        return None
    base_subject = subjects[0]
    primary = _versioned_subject(base_subject, clean_title)
    facet = _facet(clean_title)
    context = _context(facet)
    return MicrotopicIdentity(
        domain=_DOMAIN_BY_SUBJECT.get(base_subject, "AI products and research"),
        facet=facet,
        primary_entity=primary,
        secondary_entities=tuple(subject for subject in subjects[1:] if subject != primary),
        audience=_audience(f"{clean_title} {document.description[:1_200]}"),
        user_problem=context,
        core_claim=_claim(facet),
        workflow_context=context,
        content_format=_content_format(document.title),
    )


def topic_key_v7(identity: MicrotopicIdentity) -> str:
    fingerprint = "|".join(
        (
            identity.domain.lower(),
            identity.primary_entity.lower(),
            identity.facet,
            identity.workflow_context,
        )
    )
    return f"micro-v7-{sha256(fingerprint.encode()).hexdigest()[:18]}"


def _label(identity: MicrotopicIdentity) -> str:
    suffix = {
        "safety_ethics": "safety and ethics",
        "release_wave": "release wave",
        "benchmark": "performance comparisons",
        "capability_wave": "capability wave",
        "research_result": "research results",
        "adoption": "domain adoption",
        "practical_use": "practical implementations",
        "market_activity": "creator activity",
    }[identity.facet]
    return f"{identity.primary_entity} {suffix}"


def _specificity(identity: MicrotopicIdentity, document_count: int) -> float:
    named = identity.primary_entity not in _GENERIC_SUBJECTS
    substantive = identity.facet != "market_activity"
    score = 46.0 + (24 if named else 8) + (16 if substantive else 0)
    return round(min(100.0, score + min(document_count * 2, 10)), 1)


def cluster_microtopics_v7(documents: list[MicrotopicDocument]) -> list[MicrotopicCluster]:
    identities: dict[str, MicrotopicIdentity] = {}
    grouped: defaultdict[tuple[str, str, str, str], list[MicrotopicDocument]] = defaultdict(list)
    for document in documents:
        identity = infer_microtopic_identity_v7(document)
        if identity is None:
            continue
        identities[document.id] = identity
        grouped[
            (
                identity.domain,
                identity.primary_entity,
                identity.facet,
                identity.workflow_context,
            )
        ].append(document)

    clusters: list[MicrotopicCluster] = []
    for members in grouped.values():
        identity = identities[members[0].id]
        specificity = _specificity(identity, len(members))
        reasons: list[str] = []
        if identity.primary_entity in _GENERIC_SUBJECTS:
            reasons.append("generic_subject_not_a_microtrend")
        if identity.primary_entity in _DOMAIN_SUBJECTS and identity.facet == "market_activity":
            reasons.append("domain_subject_without_substantive_context")
        if specificity < 70:
            reasons.append("specificity_below_visible_floor")
        formats = Counter(identities[member.id].content_format for member in members)
        secondary = tuple(
            dict.fromkeys(
                entity
                for member in members
                for entity in identities[member.id].secondary_entities
                if entity != identity.primary_entity
            )
        )
        label = _label(identity)
        clusters.append(
            MicrotopicCluster(
                key=topic_key_v7(identity),
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
                    f"Stored titles show {label.lower()}; presentation format is excluded "
                    f"from the identity shared by {len(members)} videos."
                ),
                thesis_support_ratio=1.0,
                visible=not reasons,
                reason_codes=tuple(reasons or ("format_neutral_subject_context_supported",)),
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
    "MICROTOPIC_V7_VERSION",
    "cluster_microtopics_v7",
    "infer_microtopic_identity_v7",
    "normalize_format_neutral_title",
    "topic_key_v7",
]
