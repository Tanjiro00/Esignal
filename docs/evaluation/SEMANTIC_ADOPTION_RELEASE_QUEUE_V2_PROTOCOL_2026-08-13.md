# Semantic adoption release queue v2 — frozen protocol

Frozen: 2026-08-13, before generating the v2 derived artifact.

## Status and source boundary

This protocol supersedes the first permissive pre-audit diagnostic. It derives
an internal review queue from the prospective adoption cohort fixed at SHA-256
`855196773f240b1024ba429ff804c2da284c336cad31f4b1204d6bb144a6a539`.
It does not read future videos or outcomes and does not change candidate
membership, rank, raw logit, or the 42-day outcome definition.

This is an evidence-quality development layer, not a blind predictive holdout.
The v2 generic-anchor list was expanded after inspecting v1 pre-audit failures;
the future adoption outcome remains unopened and embargoed until 2026-09-24.

## Deterministic pre-audit

Only the frozen top quintile enters this queue. Stored evidence exemplars are
collapsed into near-copy families at token Jaccard `0.72` or containment
`0.82`. A candidate is eligible for agent audit only with:

- at least two independent title families;
- at least two channels after copy-family collapse;
- one substantive anchor concept present in at least two families;
- non-English evidence-family share at or below `0.34`.

The frozen anchor stoplist excludes:

- video-format and category terms such as `tutorial`, `review`, `agent`,
  `model`, `generator`, `workflow`, and `filmmaking`;
- offer/hype terms such as `free`, `unlimited`, `best`, `insane`, `shocked`,
  `viral`, `no limits`, and `changes everything`;
- editorial/common words such as `tested`, `news`, `updates`, `why`, `reason`,
  `every`, and `that`;
- country-only descriptors such as `China` and `Chinese`.

Concrete named products, mechanisms, audience problems, and technical
properties remain valid anchors. Small deterministic alias groups normalize
inflections such as `translate/translation`, `dub/dubbing`,
`subscription/subscriptions`, and `local/locally`.

## Agent boundary

`eligible_for_agent_audit` is not a release decision. The required sequence is:

1. Evidence Analyst: assemble stored facts, contradictions, copy-family counts,
   metrics, and URLs.
2. Trend Taxonomist: produce a stable, precise, format-neutral subject label.
3. Skeptic/Auditor: reject broad categories, copied headline waves,
   unsupported causality, and observations that do not change a creator
   decision.
4. Creator Strategist: after workspace fit, find a channel-specific content gap
   and cite the stored evidence.

Missing or rejected stages must abstain. LLMs may summarize and audit stored
evidence; they may not set deterministic adoption scores.

## Operational invocation

Run the audit from the repository root as a Python module. Directly executing
`scripts/audit_semantic_release_queue.py` is unsupported because Python then
places only the `scripts` directory, rather than the monorepo root, first on
the import path.

Local invocation:

```bash
make audit-semantic-release-queue \
  SOURCE=docs/evaluation/semantic_adoption_prospective_2026-08-13/SEMANTIC_ADOPTION_RELEASE_QUEUE_V2_2026-08-13.json \
  OUTPUT=var/evaluation/semantic-adoption-agent-audit.json \
  LIMIT=8
```

Production-container invocation:

```bash
docker compose --env-file .env.production -f docker-compose.production.yml \
  run --rm --no-deps -v /absolute/evaluation/path:/eval worker \
  uv run --no-sync python -m scripts.audit_semantic_release_queue \
  --source /eval/SEMANTIC_ADOPTION_RELEASE_QUEUE_V2_2026-08-13.json \
  --output /eval/SEMANTIC_ADOPTION_AGENT_AUDIT.json \
  --limit 8
```

The command must retain the configured rolling token caps. A skipped stage is
an abstention, not permission to raise a budget or bypass the audit.

## Product and evaluation boundary

- All candidates remain shadow-only and `product_release_ready=false`.
- Numerical probability and automatic `Act` remain prohibited.
- Candidate rank and evidence quality must be displayed as separate concepts.
- On or after 2026-09-24, evaluate adoption precision/lift and lead time
  separately from pre-audit coverage and auditor precision.
