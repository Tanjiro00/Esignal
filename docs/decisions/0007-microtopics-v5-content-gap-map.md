# ADR 0007: Microtopic identity v5 and evidence-backed content gaps

- Status: Accepted implementation
- Date: 2026-07-28
- Scope: Product improvement Slice 5
- Feature flag: `FEATURE_MICROTOPIC_CONTENT_GAP`
- Clustering version: `microtopic-clustering-v5`
- Pattern version: `topic-content-pattern-v1`
- Gap version: `content-gap-v1`
- Ranking version: `opportunity-ranking-v2`

## Context

Earlier clustering could group videos by a broad domain and surface generic
ideas such as “make a tutorial” or “compare the tools.” Semantic similarity by
itself did not prove that videos addressed the same audience, user problem, or
claim. The opportunity list also did not explain which content cells were
already occupied and which evidence-backed cell remained open.

## Decision

Each v5 topic has a stored identity containing:

- domain and facet;
- primary and secondary entities;
- target audience;
- user problem;
- core claim;
- workflow context;
- observed format distribution.

Split and merge decisions compare those identity fields in addition to semantic
and temporal overlap. Broad release or comparison clusters without a product
anchor are rejected. User-visible topics require specificity of at least 70 and
thesis support of at least 0.8.

For every evidence video, the worker persists a content pattern over audience,
claim, format, context, emotion, product anchor, proof type, and production
complexity. The channel-specific map then stores the dominant occupied cells
and three ranked open cells. Each opportunity contains:

- occupied pattern;
- proposed open gap;
- explicit differentiation;
- stored evidence references;
- ranking components;
- a reason for being primary or for ranking below the primary option.

The ranking remains deterministic. LLM output cannot set trend, gap, or
opportunity scores.

## Feedback and review support

Existing admin split and merge actions retain their audit trail. Selecting an
opportunity persists its stable `opportunity_id` on the content brief and in the
product event metadata. Slice 6 adds structured decision reasons and evaluation
labels over the same stable topic and opportunity identifiers.

## Demo isolation

Demo topics use `demo-microtopic-v5` and synthetic, explicitly demo-only
evidence. Demo content patterns and gaps are persisted in the same typed tables
so the product can be evaluated without credentials, while `source_kind=demo`
keeps them isolated from live provider data.

## Rollout and rollback

Rollout order:

1. migrate additive topic columns and content-gap tables;
2. deploy API and worker with the flag off;
3. run the v5 worker and inspect accepted/rejected expert fixtures;
4. enable the flag and regenerate signals;
5. verify primary opportunity evidence and decision-card language.

Rollback disables `FEATURE_MICROTOPIC_CONTENT_GAP`. The v4 clustering and legacy
opportunity templates remain intact, and additive stored rows can remain for
audit and later replay.

## Consequences and limitations

- Visible trends become narrower and more actionable.
- Opportunity recommendations explain what is missing instead of repeating
  generic content formats.
- Exact identity inference is deterministic and intentionally conservative.
- Pattern diversity depends on stored titles, descriptions, and transcripts.
- Channel constraints still use the v1 profile; Slice 7 adds explicit
  feasibility and absolute publish-by dates.
