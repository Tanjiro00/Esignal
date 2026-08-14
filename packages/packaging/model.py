from __future__ import annotations

from copy import deepcopy
from typing import Any

PACKAGING_VERSION = "signal-packaging-v1"
PACKAGING_SECTIONS = {
    "audience_promise",
    "core_tension",
    "hook_directions",
    "title_directions",
    "thumbnail_directions",
    "proof_requirements",
    "clickbait_mismatch_risks",
    "opening_structure",
}
TITLE_STRATEGIES = (
    "experiment",
    "comparison",
    "contrarian",
    "failure_or_risk",
    "beginner_transformation",
    "cost_or_time_saving",
    "investigation",
    "expert_playbook",
    "myth_test",
    "decision_guide",
)


def _text(angle: dict[str, Any], key: str, fallback: str) -> str:
    value = angle.get(key)
    return str(value).strip() if value else fallback


def _idea(angle: dict[str, Any]) -> str:
    gap = angle.get("open_gap")
    if isinstance(gap, dict) and gap.get("label"):
        return str(gap["label"])
    return _text(angle, "title", "the selected opportunity")


def _titles(idea: str, revision: int) -> list[dict[str, str]]:
    suffix = "" if revision == 0 else f" — test #{revision + 1}"
    values = (
        f"I tested {idea} end to end{suffix}",
        f"{idea} vs the obvious alternative: a measured comparison{suffix}",
        f"The usual advice about {idea} misses the hard part{suffix}",
        f"Before you try {idea}, test these failure cases{suffix}",
        f"From zero to a working {idea}: the honest path{suffix}",
        f"Can {idea} actually save time or money? A real test{suffix}",
        f"Why {idea} is suddenly showing up everywhere{suffix}",
        f"An expert workflow for evaluating {idea}{suffix}",
        f"I tested the biggest claim behind {idea}{suffix}",
        f"Should you use {idea}? A proof-first decision guide{suffix}",
    )
    return [
        {"strategy": strategy, "text": title}
        for strategy, title in zip(TITLE_STRATEGIES, values, strict=True)
    ]


def _thumbnails(idea: str, revision: int) -> list[dict[str, str]]:
    variants = (
        {
            "strategy": "proof_object",
            "main_visual": f"The real interface, output, or artifact used to test {idea}",
            "emotion": "Focused skepticism",
            "contrast": "Expected result vs observed result",
            "text": "REAL TEST",
            "proof_object": "A legible before/after output from the actual workflow",
            "avoid": "Fake dashboards, invented metrics, logos presented as proof",
        },
        {
            "strategy": "decision_split",
            "main_visual": "Two concrete choices separated by a hard vertical divide",
            "emotion": "Decision tension",
            "contrast": "Common approach vs selected open angle",
            "text": "WHICH WORKS?",
            "proof_object": "The two real products, files, or workflow states compared",
            "avoid": "A winner badge before the comparison has been run",
        },
        {
            "strategy": "failure_reveal",
            "main_visual": f"One visible failure point in the {idea} workflow",
            "emotion": "Useful surprise",
            "contrast": "Polished promise vs concrete limitation",
            "text": "THE CATCH",
            "proof_object": "A reproducible error, limitation, or verification step",
            "avoid": "Fabricated error messages or exaggerated facial reactions",
        },
    )
    if revision == 0:
        return [dict(item) for item in variants]
    rotated = variants[revision % len(variants) :] + variants[: revision % len(variants)]
    return [dict(item) for item in rotated]


def build_signal_packaging(
    *,
    angle: dict[str, Any],
    evidence_ids: list[str],
    revision: int = 0,
) -> dict[str, Any]:
    idea = _idea(angle)
    audience_promise = _text(
        angle,
        "audience_promise",
        f"A proof-led decision about whether {idea} is useful for the intended workflow.",
    )
    unanswered = _text(
        angle,
        "unanswered_question",
        f"What does real-world evidence show about {idea}?",
    )
    differentiation = _text(
        angle,
        "differentiation",
        "Use original proof instead of repeating the dominant coverage.",
    )
    packaging = {
        "audience_promise": audience_promise,
        "core_tension": f"{unanswered} Existing coverage leaves this unresolved: {differentiation}",
        "hook_directions": [
            {
                "strategy": "show_the_gap",
                "direction": (
                    "Open with the exact unanswered decision, then show the proof "
                    "artifact the video will use to resolve it."
                ),
            },
            {
                "strategy": "stress_test",
                "direction": (
                    f"State the strongest defensible claim about {idea}, then define "
                    "the failure condition before showing any result."
                ),
            },
            {
                "strategy": "consequence_first",
                "direction": (
                    "Start with what the audience risks getting wrong, then frame the "
                    "selected opportunity as a measured decision."
                ),
            },
        ],
        "title_directions": _titles(idea, revision),
        "thumbnail_directions": _thumbnails(idea, revision),
        "proof_requirements": [
            "Show the real product, workflow, or artifact named by the opportunity.",
            "Define the evaluation method before making a comparative claim.",
            "Replace every numeric result with measured evidence from this production.",
            f"Keep stored evidence traceable to: {', '.join(evidence_ids) or 'the linked brief'}.",
        ],
        "clickbait_mismatch_risks": [
            "Do not imply a successful result before the test has been completed.",
            "Do not invent numbers, savings, or performance improvements.",
            "Do not promise a universal outcome from channel-relative evidence.",
            "Do not make the thumbnail declare a winner the video has not proved.",
        ],
        "opening_structure": [
            "0:00–0:20 — audience decision and the unresolved tension",
            "0:20–0:45 — what will be tested and what would count as failure",
            "0:45–1:20 — evidence context and why the timing matters",
            "1:20 onward — original proof, trade-offs, and a bounded conclusion",
        ],
        "claims_policy": {
            "allowed": [
                audience_promise,
                unanswered,
                "The topic has stored evidence linked to the selected opportunity.",
            ],
            "requires_new_proof": [
                "Performance, revenue, retention, or time-saving outcomes",
                "A product or workflow winner",
                "Guaranteed audience results",
            ],
        },
        "full_script_generated": False,
        "revision": revision,
        "version": PACKAGING_VERSION,
    }
    return packaging


def regenerate_packaging_section(
    *,
    current: dict[str, Any],
    section: str,
    angle: dict[str, Any],
    evidence_ids: list[str],
    revision: int,
) -> dict[str, Any]:
    if section not in PACKAGING_SECTIONS:
        raise ValueError(f"Unsupported packaging section: {section}")
    fresh = build_signal_packaging(
        angle=angle,
        evidence_ids=evidence_ids,
        revision=revision,
    )
    updated = deepcopy(current)
    updated[section] = fresh[section]
    updated["revision"] = max(int(current.get("revision", 0)), revision)
    updated["version"] = PACKAGING_VERSION
    updated["full_script_generated"] = False
    return updated
