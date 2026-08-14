# ADR 0022: Transparent, sample-gated outcome comparators

Status: accepted

## Context

Results previously displayed a strong percentage such as `+100%` from a saved
ratio without showing the comparator sample, measurement window, or selection
method. The outcome automation already built a comparable baseline, but after a
suggestion was confirmed it stored only the derived performance metrics on the
outcome. The sample size, selected video IDs, filters, and per-horizon median
remained on the suggestion and were not available to the Results UI.

This made the percentage difficult to audit and allowed a small or legacy
sample to look as authoritative as a well-supported comparison.

## Decision

Outcome metrics version `outcome-metrics-v2` stores the complete deterministic
baseline under `performance_json.comparator`.

The comparator selects prior owned-channel uploads with:

- the same content type: long-form, Short, or live;
- duration between `0.6x` and `1.6x` of the target;
- the same sponsorship class;
- topic-family proximity ranked by title-token similarity;
- publication during the previous 180 days;
- a maximum of 20 videos.

The baseline is not broadened when few comparable videos are available.
Insufficient evidence is represented explicitly instead.

For each measurement horizon the comparator stores:

- the median view count;
- the number of videos with a usable snapshot;
- `stable` or `early` state.

Five usable videos at the selected horizon are required for a stable
comparison. The threshold is deterministic and versioned with the comparator.
Outcome automation may calculate an internal ratio for an early sample, but it
does not classify the outcome as successful, mixed, or unsuccessful until the
sample is stable.

Results displays:

- observed views and their measurement horizon;
- the comparable median at the same horizon;
- the associated percentage difference only for a stable sample;
- the exact sample size;
- the six-month period;
- the duration and topic-family matching method.

For a smaller sample the UI shows:

`Early result — not enough comparable videos for a stable uplift estimate`

and states the current and required sample sizes. No percentage is rendered.
Legacy outcome metrics without a stored comparator fail closed into this early
state.

All copy remains non-causal. The comparison describes association with a
published result and never claims that EarlySignal caused the performance.

## Consequences

- Every visible percentage resolves to stored target views, median views,
  sample size, and filters.
- A baseline sample cannot silently include old or structurally different
  videos to manufacture stability.
- Sample size is horizon-specific, so missing 24-hour snapshots cannot borrow
  credibility from later snapshots.
- Existing JSON storage remains compatible and no database migration is
  required.
- Existing `outcome-metrics-v1` rows remain readable but do not show a strong
  percentage until outcome automation refreshes them with v2 evidence.

## Verification

Backend unit coverage verifies exclusions, the six-month boundary,
horizon-specific sample counts, the five-video threshold, and preservation of
the complete comparator in associated metrics.

Frontend unit coverage verifies stable, early, and legacy states. End-to-end
coverage verifies the visible 24-hour value, comparable median, methodology,
non-causal copy, details interaction, suppressed small-sample percentage, and
390×844 layout without horizontal overflow.

Desktop, focused comparator, early-state, and mobile captures are stored under
`docs/post-audit-slice-6/screenshots/`.

## Rollback

Restore `outcome-metrics-v1`, remove the nested comparator from associated
metrics, and restore the previous ratio-only Results aside. Stored v2 JSON can
remain in existing rows because unknown keys are backward-compatible.
