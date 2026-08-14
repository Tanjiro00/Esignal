# ADR 0026: Temporal replay with blind outcome labels

- Status: accepted
- Date: 2026-08-07
- Related: ADR 0024, ADR 0025

## Context

EarlySignal must prove that historical recommendations were early and useful. A
report built from current `Topic` or `Signal` rows would leak later labels,
synthesis, status, and evidence into the past. Treating incomplete follow-up as
a failed outcome would also inflate false positives.

The implementation plan sets a quality gate before further product expansion:
precision@10 at least 40% and median lead time at least 21 days across 6–8
checkpoints.

## Decision

1. Replay predictions only from the latest `TopicSnapshot` recorded at or before
   a checkpoint. Current mutable topic and signal copies are excluded.
2. Reuse the production score recorded in that historical snapshot. This keeps
   the first replay faithful to what production knew then.
3. Rank only snapshots that satisfy the historical production visibility gate.
4. Run outcome labeling in a separate component that never queries or accepts
   prediction ranks or scores.
5. Label a topic as fired only when one future observation jointly reaches:
   - 72-hour video supply growth of at least 3x versus the checkpoint baseline;
   - median outlier lift of at least 3.
6. Do not call an outcome negative until the configured horizon is complete and
   evidence reaches its end. Incomplete histories are excluded from precision.
7. Persist immutable evaluated outcomes, evidence hashes, metrics, gate checks,
   and the generated Markdown report. Preliminary follow-up may mature forward
   in time but can never move backward.
8. The automated gate also requires at least six checkpoints and at least 80%
   evaluated prediction coverage. A report without that coverage is marked
   `insufficient_data`, not a quality failure.

## Consequences

- Future topic labels and future scores cannot affect historical ranking.
- Precision, recall, lead time, and coverage remain auditable to snapshot IDs.
- The system cannot claim validated quality from a recent checkpoint without a
  complete outcome horizon.
- This is not yet a full raw-evidence re-clustering backtest. Historical topic
  snapshots are an honest intermediate layer. A stricter later slice will replay
  clustering and measurements from the raw/normalized evidence manifest.
