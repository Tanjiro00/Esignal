# EarlySignal external 30-day historical backtest protocol

**Status:** pre-registered before outcome calculation  
**Protocol version:** `external-youtube-timeseries-replay-v1`  
**Outcome version:** `external-blind-supply-lift-30d-v1`

## Question

If the deterministic EarlySignal topic pipeline is run at a historical cutoff using only
information available at that time, do its highest-ranked topics become viral themes during the
next 30 days more often than simple rankings?

## Independent dataset

- Source: Gustav Sloth, Aarhus University, *YouTube Videos With View Count Time Series*, Zenodo
  DOI `10.5281/zenodo.14602718`, CC BY 4.0.
- Dataset file: `videos.pkl`, 62,389 videos with daily cumulative public view observations.
- Collector evidence: the source code scans videos whose `videoPublishedAt` date equals the
  previous UTC day, then records public view counts daily. The dataset does not persist exact
  `publishedAt`, so replay uses `first_observed_at - 1 day` as a documented approximation.
- Expected SHA-256 of the downloaded input:
  `be74d041d5bada889015682e9d69e88f61e2b37c9b41ca7fb9adcc72ae9768f8`.

## Frozen checkpoints

All cutoffs are end-of-day UTC. The split is chronological and fixed before labels are calculated.

| # | Cutoff | Split |
|---:|---|---|
| 1 | 2024-10-14 | train |
| 2 | 2024-10-19 | train |
| 3 | 2024-10-24 | train |
| 4 | 2024-10-29 | train |
| 5 | 2024-11-03 | train |
| 6 | 2024-11-08 | train |
| 7 | 2024-11-13 | holdout |
| 8 | 2024-11-18 | holdout |

The last outcome window ends on 2024-12-18, inside the archive's observation period.

## Point-in-time feature policy

At cutoff `t0`, feature computation may read only:

- titles and channel metadata for videos discovered by `t0`;
- view snapshots with `observed_at <= t0`;
- channel baselines constructed only from snapshots available by `t0`;
- videos approximated as published inside the preceding 30 days.

The replay reuses production `microtopic-clustering-v5`, `TopicMeasurements`, `score_topic`, and
the current production actionability gate. Missing external fields are neutralized explicitly:
audience demand and transcript coverage are zero; provider coverage is one.

## Blind outcome

For each actionable topic at `t0`, the outcome pass alone reads the following 30 days. A theme
fires only when the same stored topic identity simultaneously reaches:

1. `video_count_72h / video_count_72h_at_t0 >= 3`, and
2. channel-normalized median outlier lift `>= 3`.

Later observations are never feature inputs. Missing future evidence is not converted to success.

## Compared rankings

Each method ranks the same actionable candidate set and selects at most ten topics:

1. `method`: EarlySignal production score;
2. `supply`: recent 72-hour video count;
3. `velocity`: aggregate early view velocity;
4. `outlier`: median channel-normalized outlier lift;
5. candidate base rate: expected precision of random selection from the same set.

## Pre-registered verdict

The hypothesis is supported only if, across the eight checkpoints:

- `precision@10 >= 40%`;
- median time from signal to firing is at least 21 days;
- the method beats candidate base rate and is not worse than every simple baseline;
- at least six checkpoints contain evaluable predictions.

Train and holdout metrics are shown separately. No threshold or weight change is permitted after
holdout calculation in this run.

## Known boundary

This is a direct test of the deterministic topic/score hypothesis, not of the entire commercial
product. The archive has no comments, transcripts, descriptions, search-result occurrences,
provider diversity, exact channel IDs, or channel-specific creator fit. Those features cannot be
invented and are kept neutral. A positive result would support the core method; a negative result
would reject the current deterministic core on this external sample.
