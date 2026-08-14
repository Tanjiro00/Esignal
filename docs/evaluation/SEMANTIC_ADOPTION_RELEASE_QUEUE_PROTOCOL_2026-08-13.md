# Semantic adoption release-queue protocol

Frozen: 2026-08-13, before generating the derived release queue.

## Purpose

Turn the already-frozen prospective adoption ranking into an evidence-review
queue without changing its candidates, ranks, scores, outcome definition, or
42-day embargo. This is a product-quality layer, not a new predictive test.

The source artifact is fixed at SHA-256
`855196773f240b1024ba429ff804c2da284c336cad31f4b1204d6bb144a6a539`.
No future video or outcome may be read when producing this queue.

## Deterministic pre-audit

Only candidates in the frozen top quintile are considered. Their stored
evidence exemplars are grouped into near-copy families with token Jaccard
`0.72` or containment `0.82`. A candidate proceeds only when it has:

- at least two independent title families;
- at least two channels after copy-family collapse;
- a substantive non-generic anchor concept present in at least two families;
- no more than 34% evidence families identified as non-English by the frozen
  deterministic title heuristic.

Generic presentation words such as `tutorial`, `review`, `agent`, `model`,
`generator`, `workflow`, `free`, and `unlimited` cannot be shared anchors.
Small deterministic alias groups normalize inflections such as
`translate/translator/translation`, `dub/dubbing`, and
`subscription/subscriptions`.

The heuristic is intentionally a permissive pre-audit. It may send a weak
candidate to review, but it must not release one to a user.

## Agent release sequence

A pre-audit pass means `eligible_for_agent_audit`, never `release_ready`.
The immutable next stages are:

1. **Evidence Analyst** assembles only stored cluster evidence, metrics,
   contradictions, copy-family counts, and URLs.
2. **Trend Taxonomist** writes a neutral concrete subject label. It may not
   encode a creator stance or video format.
3. **Skeptic/Auditor** accepts only when at least two independent evidence
   families support the same narrow phenomenon and the result is neither a
   generic category nor a copied headline wave.
4. **Creator Strategist** runs only after a specific workspace/channel is
   known. It identifies a channel-specific content gap and must cite stored
   evidence.

Any missing, rejected, or unavailable stage produces abstention. LLM output may
name, summarize, and audit evidence; it may not alter the deterministic
adoption rank or outcome.

## Product boundary and evaluation

- Numeric adoption probability remains prohibited.
- `Act` remains prohibited for this shadow cohort.
- The release queue remains internal until both the agent audit and the
  prospective outcome evaluation complete.
- Outcomes remain embargoed until `2026-09-24T00:00:00Z`.
- Report separately: pre-audit coverage, auditor acceptance, evidence-quality
  false positives, adoption precision/lift, and lead time.

This protocol was designed after inspecting evidence-quality failures in the
first frozen queue. Therefore its evidence-quality behavior is developmental,
not a blind quality holdout. It does not consume or relabel the future adoption
outcome.
