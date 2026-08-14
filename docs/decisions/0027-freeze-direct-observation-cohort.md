# ADR 0027: Freeze a direct-observation train/holdout cohort

- Status: Accepted
- Date: 2026-08-07
- Decision owners: EarlySignal engineering

## Context

The implementation plan requires six to eight historical checkpoints, blind
outcome labels, a frozen code/data identity, and a final holdout evaluation.
Production has a large historical video catalogue, but direct snapshots and
topic measurements only started on 27 July 2026. No checkpoint currently has a
complete 42-day post-window.

YouTube historical search can recover published video identifiers and current
metadata. It cannot reconstruct views-at-age or prove what the system observed
at a historical timestamp. Treating such a backfill as direct evidence would
create look-ahead bias.

## Decision

1. Freeze eight checkpoints from dates that contain direct observations and at
   least one historically visible prediction candidate.
2. Persist the immutable point-in-time manifest and top-10 predictions before
   opening outcome evidence.
3. Split checkpoints chronologically: the first six are train and the last two
   are holdout.
4. Keep all outcomes unopened until their 42-day windows mature. Missing
   follow-up is `insufficient_followup`, never a negative label.
5. Hash checkpoint manifests, prediction evidence, policy versions, and the
   repository tree into one cohort dataset identity.
6. Report incomplete data as `N/A`/pending and prohibit predictive-quality
   claims before the full outcome window.
7. Do not use historical subscriber counts as a channel-size stratum because
   they were not snapshotted point-in-time.
8. Reject a future `freeze_at`. Otherwise evidence that arrives while a run is
   in progress can fall inside the requested cutoff and make identical commands
   resolve to different datasets.
9. Do not hash mutable normalized video metadata or use current publication and
   channel fields to decide historical eligibility. The stable video identity
   and first-discovery timestamp define the normalized universe; historical
   metadata must resolve from raw payloads and field provenance.

## Consequences

- A reproducible train/holdout dataset begins accumulating ground truth now.
- The earliest cohort outcomes become evaluable in September 2026.
- Historical search remains useful for catalogue/supply research, but does not
  upgrade backfilled counters to direct point-in-time evidence.
- The current provisional replay still uses scores recorded in historical topic
  snapshots. Re-clustering raw evidence with an end-to-end `as_of_date` remains
  a stricter validation layer before a final scientific quality claim.
- The `(observed_at, topic_id)` topic-snapshot index makes repeated temporal
  checkpoint queries bounded in the database instead of loading the full
  snapshot history into Python.
