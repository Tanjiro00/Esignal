# ADR 0008: Structured decision feedback and point-in-time evaluation

- Status: Accepted implementation
- Date: 2026-07-28
- Scope: Product improvement Slice 6 and P0.10
- Feature flags:
  - `FEATURE_FEEDBACK_EVALUATION`
  - `FEATURE_TOPIC_SNAPSHOT_BUCKETS`
- Feedback version: `decision-feedback-v1`
- Label version: `manual-topic-evaluation-v1`
- Bucket version: `topic-snapshot-buckets-v1`

## Decision feedback

Act, Watch, and Skip accept an optional reason from an action-specific taxonomy
and an optional 300-character note. The selected opportunity ID is stored with
the action. The UI suggests the reason immediately after the decision and lets
the user continue without one.

Reasons are validated while the feature is enabled. Legacy Save and Dismiss
actions remain compatible. Feedback is available through the admin report and
JSONL/CSV exports. Small samples never mutate production model weights.

## Manual evaluation

Evaluation labels are stored separately from production topics and signals.
The first review freezes:

- `as_of`;
- topic identity and specificity;
- latest measurement at or before `as_of`;
- evidence memberships assigned at or before `as_of`;
- demand evidence first observed at or before `as_of`;
- signal, channel-fit, opportunity, and model versions available at `as_of`.

Editing the expert judgment updates the label and notes but does not rebuild the
frozen evidence snapshot. This prevents future measurements leaking into the
review.

The admin queue loads 100 candidates by default and supports 200 per page. It
reports precision, recall on the reviewed candidate universe, precision@3,
late-signal rate, false-positive rate, topic split error rate, demand relevance
precision, and opportunity actionability rate.

A committed 100-topic regression fixture and an initial before/after report
exercise all primary labels. They are explicitly regression scenarios, not a
claim about live accuracy.

## Timeline aggregation

Raw `topic_snapshots` remain immutable. Additive buckets use:

- 15 minutes for the latest 6 hours;
- 1 hour for the latest 72 hours;
- 6 hours for the latest 14 days;
- 1 day for older history.

Each bucket stores first, last, minimum, maximum, average, current counts, score,
momentum, saturation, stage, and every source measurement ID. Ordering and
bucket boundaries are deterministic. User timelines consume the buckets only
when the flag is enabled and fall back to raw measurements if no backfill exists.

## Rollout and rollback

1. Apply additive migration.
2. Backfill timeline buckets for demo and live data.
3. Enable feedback/evaluation and verify exports.
4. Enable bucketed timelines and compare the visible series to raw evidence.
5. Collect at least 100 live reviews before considering any model change.

Rollback disables the two flags. Raw snapshots, legacy actions, and production
scores remain unchanged.
