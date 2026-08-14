# ADR 0004: Human signal review and publication gate

- Status: Accepted implementation
- Date: 2026-07-28
- Scope: Product improvement Slice 2
- Feature flag: `FEATURE_SIGNAL_REVIEW_QUEUE`
- Review version: `signal-review-v1`

## Context

Deterministic scoring can rank evidence, but it cannot reliably decide whether a
machine-formed topic is coherent, timely, sufficiently supported, and useful to
a specific creator. Publishing every candidate would turn clustering mistakes,
late trends, and weak evidence into user-facing product claims.

Slice 2 requires a human quality-control boundary. A live signal must not appear
in the feed, detail page, digest, action loop, brief flow, or outcome flow until
it has been explicitly approved for that workspace.

## Decision

Review state is workspace-scoped and separate from the internal signal pipeline:

- `signal_reviews` stores the current review state, reviewer, structured reasons,
  optional user-facing overrides, timestamps, and review version.
- `signal_review_events` is an append-only audit trail. Every queue, edit,
  decision, and publication event stores the state transition, reasons,
  provenance, changes, reviewer, and a unique idempotency key.

The supported states are:

`internal_candidate`, `needs_review`, `approved`, `rejected`, `needs_changes`,
`published`, and `expired`.

Only `approved` and `published` are user-visible when the feature flag is on.
The signal's existing pipeline status remains responsible for active/archive
processing; review status is responsible for workspace publication.

## Review workspace

`/admin/review` provides:

- status and source filters;
- queue totals, approval rate, rejection reasons, review time, and lifecycle
  distribution;
- stored video, transcript, demand, saturation, and lifecycle evidence;
- deterministic false-positive risk prompts;
- approve and reject actions;
- split, merge, late, weak-evidence, and irrelevant-demand actions;
- thesis, primary opportunity, and evidence-selection edits;
- a user-facing decision-card preview;
- complete audit history.

Bulk approval is intentionally absent. Each approval must resolve to a single
stored signal and reviewer action.

## Reason taxonomy

Structured reasons include false topic merge, overly broad or narrow topics,
late signals, single-channel or single-video dependency, weak outlier evidence,
weak or irrelevant demand, low channel fit, saturation, insufficient evidence,
duplicates, and an explicit fallback reason.

These codes are persisted on current review state and decision events so false
positives can be analyzed by failure mode and lifecycle stage.

## Demo and rollout behavior

Deterministic demo signals are auto-approved with a synthetic, audited
`auto_approved_demo` event. This keeps credential-free demo flows repeatable
without weakening the live-data boundary.

When the feature flag is off, existing user behavior is unchanged and admin
review endpoints return `404`. When it is enabled:

1. existing active live signals are lazily and idempotently queued as
   `needs_review`;
2. new live candidates are queued by the topic pipeline;
3. feed/source selection, signal detail, earlyness, actions, briefs, outcomes,
   and digest generation require approval;
4. approval records the first evidence-backed signal-visible lifecycle
   timestamp;
5. linking a published outcome advances the review to `published`.

## Consequences

- No unreviewed live candidate can leak through the main decision surfaces.
- Reviewer edits remain evidence-backed overrides instead of modifying raw
  provider or deterministic scoring records.
- Review outcomes create a labeled false-positive dataset for later
  improvements without allowing an LLM to set deterministic scores.
- Production enablement can temporarily fall back to audited demo signals until
  a human approves live candidates.
