# ADR 0025: Point-in-time backtest contract and leakage firewall

- Status: Accepted for Slice A
- Date: 2026-08-07
- Decision owners: EarlySignal engineering
- Policy version: `as-of-evidence-policy-v1`
- Manifest version: `point-in-time-checkpoint-v1`

## Context

EarlySignal has a large current-state dataset, but a historical prediction at
time `T` is valid only if every input was available at or before `T`.

Present-day normalized and derived rows are not automatically historical truth:

- channel and video metadata can be updated in place;
- video features and channel baselines keep only the latest calculation for a
  version;
- topic memberships can be reassigned;
- topic labels, lifecycle and status can change;
- topic snapshot buckets can be calculated later from backfilled history;
- LLM output may have been generated after the checkpoint;
- a comment can have an old `published_at` but a much later `created_at` in
  EarlySignal;
- historical search cannot reconstruct a missing 24-hour view counter.

Without a strict temporal contract, a backtest can look accurate while reading
future evidence.

## Decision

Every backtest checkpoint carries a timezone-aware `AsOfContext`. Source rows
are eligible only when both their domain timestamp and their EarlySignal
availability timestamp are no later than the cutoff.

### Source evidence policy

| Evidence             | Required cutoff rule                                                  | Notes                                                                                                                 |
| -------------------- | --------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Video                | `published_at <= T` and `first_discovered_at <= T`                    | Current title/description is not treated as historical truth; replay resolves values from raw payloads and provenance |
| Discovery occurrence | `discovered_at <= T`; linked fetch completed by `T`                   | Canonical evidence of when EarlySignal saw the video                                                                  |
| Provider fetch       | `completed_at <= T` and linked to an eligible source entity           | Payload hash and parser version are part of the manifest                                                              |
| Field provenance     | `observed_at <= T`; linked fetch completed by `T`                     | Preserves field-level evidence without exposing raw payloads                                                          |
| Video snapshot       | `observed_at <= T`; linked fetch completed by `T`                     | `snapshot_quality` and `is_estimated` remain explicit                                                                 |
| Snapshot job         | `completed_at <= T`                                                   | Used for direct target-age coverage, not as a view measurement                                                        |
| Comment              | `published_at <= T`, `created_at <= T`; linked fetch completed by `T` | Prevents later-fetched old comments from leaking into the checkpoint                                                  |
| Transcript           | `fetched_at <= T`; linked fetch completed by `T`                      | Video publication time alone is insufficient                                                                          |

Provider sensitivity can further restrict eligible fetches using
`allowed_providers`. Comments and transcripts have independent inclusion
switches.

### Derived data policy

These current tables are excluded from the checkpoint input hash:

- `channel_baselines`;
- `video_features`;
- `video_embeddings`;
- `topics`;
- `topic_video_memberships`;
- `topic_snapshots`;
- `comment_features`;
- `comment_topic_relevance`;
- `demand_clusters`;
- `llm_intelligence_runs`;
- `signals`;
- `workspace_signal_scores`.

They are outputs or mutable projections. The backtest harness must recompute
them from source evidence available by `T`. Historical derived rows can be used
as audit comparators, but never as prediction inputs unless a future migration
makes them immutable and records a trustworthy calculation timestamp and input
hash.

### Manifest contract

A checkpoint manifest stores:

- cutoff and source kind;
- provider/comment/transcript policy;
- deterministic per-table row counts and SHA-256 digests;
- first and last included observation timestamps;
- direct snapshot coverage and successful target-age job counts;
- database migration revision;
- code/model versions;
- repository revision and dirty state;
- deterministic hash of the Python source/migrations/dependency lock tree when
  no commit exists;
- explicit limitations;
- an `input_hash` and full `content_sha256`.

The manifest contains hashes and minimal metadata, not raw comments, transcript
text, provider payloads or credentials.

### Persistence contract

`backtest_runs`, `backtest_checkpoints`, and `backtest_predictions` are
append-only evaluation records. Repeating the same checkpoint manifest reuses
the same run via an idempotency key derived from `input_hash`.

The initial Slice A checkpoint stores zero predictions. Prediction replay and
outcome labels are later slices.

## Leakage invariants

Tests must prove that:

1. a naive cutoff is rejected;
2. adding rows with availability timestamps after `T` does not change the
   checkpoint hash;
3. adding an eligible row at or before `T` does change the input hash;
4. an old comment fetched after `T` remains excluded;
5. a transcript fetched after `T` remains excluded;
6. a snapshot observed after `T` remains excluded;
7. demo and live source records do not mix;
8. repeated persistence does not create duplicate runs or checkpoints;
9. stored manifest hashes verify before persistence.

## Consequences

Positive:

- backtest quality cannot be inflated by obvious future rows;
- every run is reproducible and versioned;
- provider sensitivity becomes a first-class parameter;
- snapshot coverage limitations remain visible;
- the current production pipeline does not change.

Costs and limitations:

- current normalized title/description history cannot be trusted without raw
  payload replay;
- current channel subscriber counters are not point-in-time facts;
- current derived tables must be recomputed, which makes replay more expensive;
- very early checkpoints may have too little direct snapshot coverage and must
  be declared ineligible rather than filled with present-day counters;
- a fully frozen code revision is impossible until the repository has a real
  commit; manifests explicitly record `uncommitted/dirty` and a source-tree
  SHA-256 meanwhile.

## Alternatives rejected

### Filter only by `published_at`

Rejected because discovery, snapshots, comments and transcripts may have been
collected much later.

### Use current topic snapshots as historical predictions

Rejected because snapshots can be backfilled and topic identity can reflect
later evidence.

### Infer missing 24-hour views from today's count

Rejected as a prediction input. Estimates may be evaluated separately but must
never be marked direct.

### Copy the production database and hide recent rows manually

Rejected because it is not a typed, testable or reproducible policy.
