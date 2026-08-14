"""Grounded verification of demand items.

Corpus statistics get a demand item as far as "this is about something
specific". They cannot tell a genuine request from a joke: on production data
"But can it run crysis?" scores 45 and "Can we upload our own character?"
scores 48. Both are questions, both are specific; only one is worth a video.

That last step is a judgement about meaning, so an LLM makes it — under strict
rules. It may classify and rephrase; it may not invent. Every verdict must quote
a comment verbatim, and a verdict whose quote is not found in the input is
discarded. The model never assigns a score and never changes ranking.

This module is pure: prompt construction and answer validation only. The call
itself belongs to the ingestion layer, which owns credentials and retries.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, replace
from typing import Any

from es_core.demand_items import DemandItem

VERIFIER_VERSION = "demand-verifier-v1"

INSTRUCTIONS = """You judge whether a group of YouTube comments is a real
request that a creator could answer with a video.

Answer "actionable" only when viewers are asking for something a video can
deliver: a how-to, an explanation, a comparison, a workaround, a decision.

Answer "not_actionable" for jokes and memes, complaints about the video or its
creator, general chatter, opinions, and questions that are not about the
subject matter (for example job-hunting questions under a technology video).

Rules you must follow:
- Quote at least one comment verbatim in "evidence". Copy it exactly.
- "need" is one neutral sentence describing what the viewers want to know.
  Describe the observed request. Do not write a video title, do not add a
  conclusion, do not use words like "best" or "ultimate".
- If the comments are too mixed to share one need, answer "not_actionable".

Return only JSON:
{"verdict": "actionable" | "not_actionable",
 "need": "<one sentence>",
 "evidence": ["<verbatim comment>", ...]}"""


@dataclass(frozen=True, slots=True)
class VerificationRequest:
    item_id: str
    payload: str


@dataclass(frozen=True, slots=True)
class Verification:
    item_id: str
    actionable: bool
    need: str
    evidence: tuple[str, ...]
    rejected_reason: str = ""

    @property
    def grounded(self) -> bool:
        return self.actionable and bool(self.evidence) and not self.rejected_reason


def build_request(item: DemandItem, *, sample: int = 8) -> VerificationRequest:
    """Render one item as the model's input: only stored comments, nothing else."""

    comments = [comment.text.strip().replace("\n", " ") for comment in item.comments[:sample]]
    body = {
        "comments": comments,
        "asked_by": item.distinct_askers,
        "across_channels": item.distinct_channels,
    }
    return VerificationRequest(
        item_id=item.item_id,
        payload=json.dumps(body, ensure_ascii=False),
    )


def _normalized(value: str) -> str:
    return " ".join(value.lower().split())


def parse_response(
    item: DemandItem,
    raw: str | dict[str, Any],
    *,
    minimum_quote_length: int = 12,
) -> Verification:
    """Validate a model answer against the stored comments.

    A quote that does not appear in the item's own comments means the model
    produced evidence rather than read it, and the whole verdict is dropped.
    """

    try:
        payload = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        return Verification(item.item_id, False, "", (), "unparseable_response")
    if not isinstance(payload, dict):
        return Verification(item.item_id, False, "", (), "unparseable_response")

    verdict = str(payload.get("verdict") or "")
    need = str(payload.get("need") or "").strip()
    raw_evidence = payload.get("evidence")
    quotes = [str(value) for value in raw_evidence] if isinstance(raw_evidence, list) else []

    if verdict not in {"actionable", "not_actionable"}:
        return Verification(item.item_id, False, need, (), "unknown_verdict")
    if verdict == "not_actionable":
        return Verification(item.item_id, False, need, ())

    haystack = [_normalized(comment.text) for comment in item.comments]
    grounded = tuple(
        quote
        for quote in quotes
        if len(_normalized(quote)) >= minimum_quote_length
        and any(_normalized(quote) in text for text in haystack)
    )
    if not grounded:
        return Verification(item.item_id, False, need, (), "ungrounded_evidence")
    if not need:
        return Verification(item.item_id, False, need, grounded, "missing_need")
    return Verification(item.item_id, True, need, grounded)


def apply(
    items: Sequence[DemandItem],
    verifications: Sequence[Verification],
) -> tuple[DemandItem, ...]:
    """Keep only items a grounded verdict cleared, and attach their phrasing.

    Unverified items are dropped rather than passed through with a warning:
    ranking an item the verifier rejected would put a joke in front of a paying
    customer, and no ordering rule downstream can undo that.
    """

    by_id = {verification.item_id: verification for verification in verifications}
    kept: list[DemandItem] = []
    for item in items:
        verification = by_id.get(item.item_id)
        if verification is None or not verification.grounded:
            continue
        kept.append(replace(item, need=verification.need))
    return tuple(kept)


def summarize(verifications: Sequence[Verification]) -> dict[str, float]:
    total = len(verifications)
    if not total:
        return {"total": 0}
    actionable = sum(1 for item in verifications if item.grounded)
    rejected = sum(1 for item in verifications if item.rejected_reason)
    return {
        "total": total,
        "actionable": actionable,
        "actionable_share": round(actionable / total, 4),
        "rejected_for_grounding": rejected,
    }


__all__ = [
    "INSTRUCTIONS",
    "VERIFIER_VERSION",
    "Verification",
    "VerificationRequest",
    "apply",
    "build_request",
    "parse_response",
    "summarize",
]
