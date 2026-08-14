# ADR 0023: Evidence-backed insight release gate

## Status

Accepted.

## Context

Production review of the Anton Nazarov workspace showed that stored trend
evidence could be real while the resulting video recommendation was still
obvious. The previous `content-gap-v1` model treated an unoccupied coverage
cell as a strong insight:

- template candidates received novelty values above 90 without measuring a
  novel observation;
- any non-empty fallback question received 90 points of unmet demand even when
  no demand cluster existed;
- the same hands-on-test template and generic “what is changing” question were
  released across unrelated topics.

This confused three different states: detected trend, plausible coverage-gap
hypothesis, and evidence-backed content insight.

## Decision

`content-gap-v4` and `opportunity-ranking-v5` separate those states.

Every angle stores:

- `release_ready`;
- `insight_status`;
- `insight_type`;
- `insight_statement`;
- `insight_reason_codes`;
- `insight_evidence`;
- `insight_metrics`.

A candidate is release-ready only when at least one supported insight path is
present:

1. A confirmed cross-video audience-demand cluster supplies the question and
   stored comment evidence.
2. A repeated channel-relative performance split may be measured across stored
   videos, but it remains analyst input and cannot release by itself. Production
   evidence showed that heuristic subject labels can still be too vague to
   support a useful creator recommendation.
3. The Evidence Analyst identifies a concrete contradiction, behavior shift,
   constraint, adoption pattern, or market-structure change supported by
   multiple stored evidence references. A separate Skeptic/Auditor must accept
   both the grounding and the editorial value before release. It rejects
   grounded but obvious restatements, requires a specific mechanism, and
   requires the insight to identify a concrete creator decision that changes.
   The LLM may summarize stored evidence but does not modify deterministic
   scores.

Personalized Evidence Analyst runs use an isolated per-workspace trace, circuit
breaker, and task budget. The scheduler runs this pass after a live topic
rebuild and before digest generation. This prevents the global topic order or
another creator's workload from consuming the analysis budget for a workspace.

An unoccupied coverage cell without one of those paths remains a candidate.
Its unmet-demand score is zero and its novelty score is capped at 44.

`evidence-digest-v4-insight-gate` excludes candidate-only topics from Today.
Legacy angles without release provenance fail closed. The Opportunities
library may retain them in the Watching group as “Insight pending”, but they
are not presented as decisions or ready video ideas.

## Consequences

- Today can be empty even when the system detects active trends.
- Fewer recommendations are expected; each released recommendation must
  explain what the evidence adds and link back to stored sources.
- Deterministic performance splits remain stored for analysis but require the
  Evidence Analyst and Skeptic/Auditor before becoming creator-facing.
- Existing production data becomes safe immediately because missing
  `release_ready` provenance is treated as candidate-only.
- Rebuilding topic intelligence populates the new insight metrics and can
  release a recommendation when the evidence floor is met.

## Verification

- Unit tests cover unsupported fallback demand, confirmed audience demand,
  subject-level performance splits, rejection of format/emotion/proof-type
  splits, and decision suppression.
- Integration tests verify additive API contracts and an empty digest when all
  angles are candidate-only.
- Browser E2E verifies the evidence-backed insight surface, source expansion,
  mobile layout, and the honest empty state.

## Rollback

Revert the content-gap and digest versions and restore the previous digest
selection. No database migration is required because all new fields are stored
inside existing JSON contracts.
