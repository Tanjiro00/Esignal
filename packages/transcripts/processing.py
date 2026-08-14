from __future__ import annotations

import re
from dataclasses import dataclass
from hashlib import sha256

from packages.clustering import embed_video_text, normalize_entities

PROCESSING_VERSION = "transcript-processing-v2"
MAX_EVIDENCE_SEGMENTS = 5
MAX_EVIDENCE_CHARACTERS = 280

SPACE_PATTERN = re.compile(r"\s+")
QUESTION_PATTERN = re.compile(
    r"\b(how|what|why|when|where|which|can|could|should|would|is|are|do|does)\b",
    re.IGNORECASE,
)
CLAIM_PATTERN = re.compile(
    r"\b(because|means|results?|costs?|faster|slower|better|worse|percent|version|model|"
    r"supports?|requires?|allows?|can|cannot|will|won't|compared|versus|vs\.?)\b|\d",
    re.IGNORECASE,
)
USE_CASE_PATTERN = re.compile(
    r"\b(use|using|workflow|build|create|generate|automate|run|deploy|edit|code|research)\b",
    re.IGNORECASE,
)
COMPARISON_PATTERN = re.compile(
    r"\b(compare|compared|comparison|versus|vs\.?|alternative|instead|better|worse)\b",
    re.IGNORECASE,
)
WORD_PATTERN = re.compile(r"[a-z0-9][a-z0-9+#.-]{2,}", re.IGNORECASE)
TITLE_STOP_WORDS = {
    "about",
    "after",
    "and",
    "best",
    "for",
    "from",
    "how",
    "made",
    "new",
    "the",
    "this",
    "with",
    "your",
}
FILLER_PATTERN = re.compile(
    r"\b(okay|actually|basically|literally|you know|kind of|sort of|um|uh)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ProcessedSegment:
    position: int
    start_seconds: float
    end_seconds: float
    text: str
    embedding: list[float]
    is_evidence: bool
    content_hash: str


@dataclass(frozen=True)
class ProcessedTranscript:
    summary: dict[str, str]
    entities: list[str]
    key_claims: list[dict[str, object]]
    use_cases: list[str]
    comparisons: list[str]
    unanswered_questions: list[str]
    narrative_angle: str
    content_format: str
    segments: list[ProcessedSegment]


def _normalized(value: str) -> str:
    return SPACE_PATTERN.sub(" ", value).strip()


def _bounded(value: str, limit: int = MAX_EVIDENCE_CHARACTERS) -> str:
    normalized = _normalized(value)
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1].rstrip()}…"


def _chunk_segments(
    segments: tuple[tuple[float, float, str], ...],
) -> list[tuple[float, float, str]]:
    chunks: list[tuple[float, float, str]] = []
    start = 0.0
    end = 0.0
    texts: list[str] = []
    for segment_start, segment_end, raw_text in segments:
        text = _normalized(raw_text)
        if not text:
            continue
        if texts and (
            segment_end - start > 35 or len(" ".join((*texts, text))) > MAX_EVIDENCE_CHARACTERS
        ):
            chunks.append((start, end, _bounded(" ".join(texts))))
            texts = []
        if not texts:
            start = segment_start
        texts.append(text)
        end = segment_end
    if texts:
        chunks.append((start, end, _bounded(" ".join(texts))))
    return chunks


def _content_format(title: str, text: str) -> str:
    haystack = f"{title} {text[:4000]}".lower()
    formats = (
        ("comparison", (" vs ", " versus ", "compare", "comparison")),
        ("tutorial", ("tutorial", "step by step", "how to", "setup", "walkthrough")),
        ("review", ("review", "tested", "my verdict", "pros and cons")),
        ("interview", ("interview", "podcast", "guest", "conversation")),
        ("news-analysis", ("news", "announced", "release", "breaking", "launch")),
        ("demo", ("demo", "watch this", "here it is", "show you")),
    )
    for label, patterns in formats:
        if any(pattern in haystack for pattern in patterns):
            return label
    return "explainer"


def _narrative_angle(content_format: str, text: str) -> str:
    lowered = text[:5000].lower()
    if "without" in lowered or "free" in lowered or "unlimited" in lowered:
        return "constraint-removal"
    if "problem" in lowered and ("solution" in lowered or "fix" in lowered):
        return "problem-solution"
    if content_format == "comparison":
        return "comparative-evaluation"
    if content_format in {"tutorial", "demo"}:
        return "practical-demonstration"
    if content_format == "news-analysis":
        return "release-analysis"
    return "evidence-led-explainer"


def _evidence_score(
    text: str,
    *,
    title_terms: set[str],
    entities: list[str],
) -> float:
    lowered = text.lower()
    relevance = sum(1.8 for term in title_terms if term in lowered)
    relevance += sum(1.4 for entity in entities if entity.lower() in lowered)
    claim = 2.0 if CLAIM_PATTERN.search(text) else 0
    use_case = 1.2 if USE_CASE_PATTERN.search(text) else 0
    comparison = 1.0 if COMPARISON_PATTERN.search(text) else 0
    detail = min(len(text) / MAX_EVIDENCE_CHARACTERS, 1)
    filler_penalty = min(len(FILLER_PATTERN.findall(text)) * 0.45, 2.2)
    return relevance + claim + use_case + comparison + detail - filler_penalty


def process_transcript(
    *,
    title: str,
    full_text: str,
    segments: tuple[tuple[float, float, str], ...],
) -> ProcessedTranscript:
    chunks = _chunk_segments(segments)
    entities = normalize_entities(title, full_text[:12_000])
    title_terms = {
        word.lower() for word in WORD_PATTERN.findall(title) if word.lower() not in TITLE_STOP_WORDS
    }
    ranked = sorted(
        enumerate(chunks),
        key=lambda item: _evidence_score(
            item[1][2],
            title_terms=title_terms,
            entities=entities,
        ),
        reverse=True,
    )
    evidence_positions = {index for index, _ in ranked[: min(MAX_EVIDENCE_SEGMENTS, len(ranked))]}
    processed = [
        ProcessedSegment(
            position=index,
            start_seconds=round(start, 3),
            end_seconds=round(end, 3),
            text=text,
            embedding=embed_video_text(text, "", entities),
            is_evidence=index in evidence_positions,
            content_hash=sha256(f"{round(start, 3)}:{round(end, 3)}:{text}".encode()).hexdigest(),
        )
        for index, (start, end, text) in enumerate(chunks)
    ]
    evidence = [item for item in processed if item.is_evidence]
    evidence.sort(key=lambda item: item.start_seconds)
    claims = [
        {
            "text": item.text,
            "start_seconds": item.start_seconds,
            "end_seconds": item.end_seconds,
        }
        for item in evidence
        if CLAIM_PATTERN.search(item.text)
    ][:3]
    use_cases = [item.text for item in evidence if USE_CASE_PATTERN.search(item.text)][:3]
    comparisons = [item.text for item in evidence if COMPARISON_PATTERN.search(item.text)][:3]
    questions = [
        item.text for item in processed if "?" in item.text or QUESTION_PATTERN.match(item.text)
    ][:3]
    summary_source = evidence[:2] or processed[:2]
    summary_text = _bounded(" ".join(item.text for item in summary_source), 480)
    content_format = _content_format(title, full_text)
    return ProcessedTranscript(
        summary={"text": summary_text, "method": "extractive"},
        entities=entities,
        key_claims=claims,
        use_cases=use_cases,
        comparisons=comparisons,
        unanswered_questions=questions,
        narrative_angle=_narrative_angle(content_format, full_text),
        content_format=content_format,
        segments=processed,
    )
