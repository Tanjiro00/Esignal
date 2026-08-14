# ADR 0003: Earlyness and append-only lifecycle history

- Status: Accepted implementation
- Date: 2026-07-28
- Scope: Product improvement Slice 1
- Feature flag: `FEATURE_EARLYNESS_TIMELINE`
- History version: `topic-lifecycle-history-v1`
- Backfill version: `topic-lifecycle-backfill-v1`

## Context

The previous UI showed a current lifecycle label and a decorative sequence of
`Day 1`, `Day 4`, and similar values. Those dates were not backed by stored
topic measurements and therefore could not prove EarlySignal's core earlyness
claim.

Slice 1 must preserve the exact point in time when a topic changed state,
backfill current topics from historical measurements, and avoid calling a
signal early when the stored visible timestamp is at or after Breakout.

## Decision

Add two additive tables:

- `topic_lifecycle_transitions` is an append-only transition log. Each row
  stores the topic, previous and next stage, timestamp, source measurement,
  score, deterministic reason codes, and history version.
- `topic_lifecycle_summaries` stores the first evidence timestamps needed by
  the user-facing earlyness contract and the evidence IDs that resolve every
  displayed milestone.

Transition IDs are deterministic. A topic measurement can create at most one
transition, and repeated backfills do not update or duplicate an existing
event.

The large-channel adoption threshold is fixed at **100,000 subscribers**. This
matches the existing topic measurement used by scoring. The threshold is
returned in the API and displayed in the UI explanation.

## Point-in-time backfill

The command is:

```bash
make backfill-lifecycle-history SOURCE=live
```

The backfill:

1. reads active topics and their stored `topic_snapshots` in chronological
   order;
2. derives the lifecycle stage from values present in each individual
   measurement;
3. writes only actual stage changes;
4. resolves first publication/discovery timestamps from current stored topic
   evidence;
5. backfills the first visible-signal timestamp only when the historical
   snapshot contains every existing hard-gate input and passes those gates;
6. leaves unknown timestamps as `null`.

It does not use later snapshots to alter earlier measurement inputs. If an old
snapshot lacks a required visibility field, the system does not guess when the
signal became visible.

## Runtime behavior

When `FEATURE_EARLYNESS_TIMELINE=true`, each new topic measurement:

- runs the idempotent backfill before the normal live topic refresh;
- appends a transition only when the stage changed;
- refreshes the first-event summary from stored evidence;
- records visibility when the existing deterministic hard gates create or
  retain a visible signal.

When the flag is off, scoring, signal visibility, and the existing API behavior
remain unchanged. The new schema is additive.

## API

Additive fields:

- signal feed items may include `earlyness`;
- signal detail may include the full `earlyness` object.

New route:

```text
GET /api/v1/workspaces/{workspace_id}/signals/{signal_id}/earlyness
```

The route is disabled with `404` while the feature flag is off.

Computed fields include:

- `lead_time_to_breakout_hours`;
- `lead_time_to_large_channel_hours`;
- `visible_age_hours`;
- `time_in_current_stage_hours`.

A positive stored interval can produce:

```text
Detected 3 days before breakout
```

If Breakout has not occurred, the response uses an explicit pending state. If
the visible timestamp is at or after Breakout, the response uses a late state
and never formats the negative interval as an early claim.

## UI

The Signals decision surface displays the earlyness headline and pending/late
context when enabled. Signal Detail replaces decorative dates with:

- an evidence-backed earlyness claim;
- a one-click lifecycle evidence disclosure;
- exact stored dates for reached milestones;
- `Not yet` or `Not observed` for missing milestones;
- an explicit explanation of the large-channel threshold.

The disabled fallback no longer invents `Day N` dates.

## Compatibility and rollback

- Existing `/api/v1` routes and raw score fields are unchanged.
- Both tables can coexist while the feature flag is off.
- The downgrade removes only the Slice 1 tables.
- No existing topic, snapshot, signal, score, evidence membership, or provider
  payload is rewritten by the migration.
- Production rollout requires a verified pre-migration backup and an explicit
  live backfill before enabling the flag.

## Known limitations

- Very old topic snapshots may not contain all hard-gate inputs. Their stage can
  still be reconstructed conservatively, but the visible-signal timestamp stays
  unknown unless it is evidenced.
- Historical memberships are not versioned separately in the current schema.
  First publication/discovery timestamps use the stored evidence membership of
  the current topic identity.
- A lifecycle correction workflow is intentionally deferred. Slice 1 does not
  mutate an existing transition; later admin correction must add an auditable
  correction event instead.
