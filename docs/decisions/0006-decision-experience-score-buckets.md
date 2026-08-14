# ADR 0006: Decision experience and user-facing score buckets

- Status: Accepted implementation
- Date: 2026-07-28
- Scope: Product improvement Slice 4
- Feature flag: `FEATURE_DECISION_EXPERIENCE`
- Decision version: `signal-decision-v1`
- Bucket version: `score-to-user-bucket-v1`

## Context

The previous user surfaces exposed raw signal and channel-fit values next to
many component metrics. This implied more precision than the stored evidence
could support and forced creators to interpret the scoring model before making
a content decision.

Digest and Signal Detail also duplicated decision heuristics. The same signal
could therefore appear actionable in one surface and uncertain in another.

## Decision

One deterministic domain module now owns the customer-facing decision:

- `score_to_user_bucket_v1` converts an internal score to `Low`, `Moderate`,
  `High`, or `Very high`;
- weak baseline coverage, high fragility, or weak topic specificity can
  downgrade the visible bucket;
- every bucket includes reason codes and a version;
- `assess_decision` combines signal strength, channel fit, evidence strength,
  lifecycle, saturation, and production feasibility into `Act`, `Watch`, or
  `Skip`.

The raw values remain stored and continue to be returned in existing API fields
for compatibility, admin review, evaluation, and calibration. New additive
`decision_card` fields are returned by feed and detail APIs while the feature
flag is enabled.

## First-screen contract

The user-facing decision card contains:

- decision;
- specific topic and one-sentence thesis;
- why now;
- why the owned channel;
- open angle and recommended video;
- publishing window and production effort;
- signal, fit, confidence, and evidence buckets;
- one main risk;
- actions for Act, Watch, and Skip.

Raw formula values, provider provenance, transcripts, and complete evidence are
not shown on the primary screen. They remain one click away under:

- View evidence;
- Why this recommendation;
- How the score was formed.

Digest is the default route. It contains at most three ranked decision cards.
Signals remains available as the research feed.

## Actions and compatibility

The signal action API accepts `act`, `watch`, and `skip`. Existing `save` and
`dismiss` values remain valid for older clients. Product events have distinct
types for the new decisions.

Digest content is versioned as `evidence-digest-v2`. When the feature is
enabled, an older digest or a v2 digest without decision cards is regenerated
before delivery.

## Rollout and rollback

Rollout order is:

1. deploy code with the feature flag off;
2. run API, unit, integration, web, and mobile e2e tests;
3. enable the flag for API and worker;
4. regenerate the latest digest;
5. inspect Act/Watch/Skip distribution and evidence downgrades.

Rollback disables `FEATURE_DECISION_EXPERIENCE`. The original raw API fields and
legacy actions remain available, and no migration is required.

## Consequences and limitations

- User surfaces no longer imply decimal precision.
- Digest and Signal Detail cannot disagree on the current decision.
- Conservative downgrades favor missed opportunities over unsupported claims.
- Current production feasibility uses the stored opportunity range and channel
  production days. Slice 7 will add richer constraints and absolute publish-by
  dates.
- Decision quality still depends on topic specificity and content-gap quality;
  those are addressed in the next slice.
