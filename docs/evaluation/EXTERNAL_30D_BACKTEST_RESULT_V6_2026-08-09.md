# EarlySignal external 30-day historical backtest

**Verdict:** FAIL  
**Dataset SHA-256:** `be74d041d5bada889015682e9d69e88f61e2b37c9b41ca7fb9adcc72ae9768f8`  
**Protocol:** `external-youtube-timeseries-replay-v3-v6-taxonomy`  
**Outcome:** `external-blind-supply-lift-30d-v1`  
**Eligible AI/tech videos:** 216  
**Stable topic identities:** 30

## Primary result

| Split | Method | Predictions | Fired | Precision@10 | Median lead |
|---|---|---:|---:|---:|---:|
| train | method | 0 | 0 | N/A | N/A |
| train | supply | 14 | 0 | 0.0% | N/A |
| train | velocity | 14 | 0 | 0.0% | N/A |
| train | outlier | 14 | 0 | 0.0% | N/A |
| train | random expected | 14 | 0 | 0.0% | N/A |
| holdout | method | 0 | 0 | N/A | N/A |
| holdout | supply | 4 | 0 | 0.0% | N/A |
| holdout | velocity | 4 | 0 | 0.0% | N/A |
| holdout | outlier | 4 | 0 | 0.0% | N/A |
| holdout | random expected | 4 | 0 | 0.0% | N/A |
| all | method | 0 | 0 | N/A | N/A |
| all | supply | 18 | 0 | 0.0% | N/A |
| all | velocity | 18 | 0 | 0.0% | N/A |
| all | outlier | 18 | 0 | 0.0% | N/A |
| all | random expected | 18 | 0 | 0.0% | N/A |

## Gate

| Check | Result |
|---|---|
| checkpoints | PASS |
| has_actionable_predictions | FAIL |
| has_positive_outcomes | FAIL |
| precision_at_10 | FAIL |
| median_lead | FAIL |
| beats_base_rate | FAIL |
| not_worse_than_all_simple_baselines | FAIL |

## Historical predictions

### 2024-10-14T23:59:59+00:00 — train

Candidates: 0

| Rank | Topic | Score | Fired | Lead | Supply peak | Lift peak |
|---:|---|---:|---|---:|---:|---:|
| — | No actionable topic | — | — | — | — | — |

Fired candidate topics:

- None

### 2024-10-19T23:59:59+00:00 — train

Candidates: 0

| Rank | Topic | Score | Fired | Lead | Supply peak | Lift peak |
|---:|---|---:|---|---:|---:|---:|
| — | No actionable topic | — | — | — | — | — |

Fired candidate topics:

- None

### 2024-10-24T23:59:59+00:00 — train

Candidates: 0

| Rank | Topic | Score | Fired | Lead | Supply peak | Lift peak |
|---:|---|---:|---|---:|---:|---:|
| — | No actionable topic | — | — | — | — | — |

Fired candidate topics:

- None

### 2024-10-29T23:59:59+00:00 — train

Candidates: 0

| Rank | Topic | Score | Fired | Lead | Supply peak | Lift peak |
|---:|---|---:|---|---:|---:|---:|
| — | No actionable topic | — | — | — | — | — |

Fired candidate topics:

- None

### 2024-11-03T23:59:59+00:00 — train

Candidates: 0

| Rank | Topic | Score | Fired | Lead | Supply peak | Lift peak |
|---:|---|---:|---|---:|---:|---:|
| — | No actionable topic | — | — | — | — | — |

Fired candidate topics:

- None

### 2024-11-08T23:59:59+00:00 — train

Candidates: 0

| Rank | Topic | Score | Fired | Lead | Supply peak | Lift peak |
|---:|---|---:|---|---:|---:|---:|
| — | No actionable topic | — | — | — | — | — |

Fired candidate topics:

- None

### 2024-11-13T23:59:59+00:00 — holdout

Candidates: 0

| Rank | Topic | Score | Fired | Lead | Supply peak | Lift peak |
|---:|---|---:|---|---:|---:|---:|
| — | No actionable topic | — | — | — | — | — |

Fired candidate topics:

- None

### 2024-11-18T23:59:59+00:00 — holdout

Candidates: 0

| Rank | Topic | Score | Fired | Lead | Supply peak | Lift peak |
|---:|---|---:|---|---:|---:|---:|
| — | No actionable topic | — | — | — | — | — |

Fired candidate topics:

- None

## Interpretation boundary

- Feature code never reads post-checkpoint snapshots; only the blind outcome pass does.
- The result tests the deterministic topic/score core, not comments, transcripts, creator fit, or provider diversity, which the external archive does not contain.
- Exact publication timestamps are approximated as first observation minus one day, matching the source collector's previous-day selection rule.
- The source archive and its collection code are independent of EarlySignal.

