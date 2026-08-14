# EarlySignal frozen historical cohort

**Cohort:** production direct-observation cohort v1  
**Cohort ID:** `a51029e6-52cc-5cc1-b227-332d5b59c439`  
**Status:** FROZEN  
**Dataset hash:** `3d6015b6fd96e4d6543a2539f43db447ee640a4530d0b9cff9265127c55b8b48`  
**Checkpoints:** 8  
**Train / holdout:** 6 / 2  
**Complete 42-day outcomes:** 0/8

| # | Split | Checkpoint | Outcome ready | Direct video coverage | Prediction candidates |
|---:|---|---|---|---:|---:|
| 1 | train | 2026-07-31T23:59:11.057367Z | 2026-09-11T23:59:11.057367Z | 100.0% | 38 |
| 2 | train | 2026-08-01T23:59:05.627851Z | 2026-09-12T23:59:05.627851Z | 100.0% | 37 |
| 3 | train | 2026-08-02T23:59:18.887888Z | 2026-09-13T23:59:18.887888Z | 100.0% | 30 |
| 4 | train | 2026-08-03T23:56:37.028905Z | 2026-09-14T23:56:37.028905Z | 100.0% | 25 |
| 5 | train | 2026-08-04T23:58:33.508059Z | 2026-09-15T23:58:33.508059Z | 100.0% | 23 |
| 6 | train | 2026-08-05T23:59:14.270411Z | 2026-09-16T23:59:14.270411Z | 100.0% | 21 |
| 7 | holdout | 2026-08-06T23:58:35.553493Z | 2026-09-17T23:58:35.553493Z | 100.0% | 18 |
| 8 | holdout | 2026-08-07T10:42:46.315556Z | 2026-09-18T10:42:46.315556Z | 100.0% | 19 |

## Freeze policy

- Only live, direct, non-estimated point-in-time observations were accepted.
- A candidate checkpoint required at least 500 eligible videos, 1,000 direct snapshots, and 10 visible prediction candidates.
- The eight latest eligible checkpoints were selected chronologically.
- The first six checkpoints are train; the last two are a sealed holdout.
- The replay stored the top 10 predictions for every checkpoint before any outcomes were opened (80 frozen predictions total).

## Interpretation

- Predictions are frozen before blind outcomes are evaluated.
- The holdout checkpoints must not be used for threshold tuning.
- No quality claim is allowed until the 42-day windows mature.
- Historical search cannot reconstruct views-at-age and is not accepted as direct point-in-time evidence.
- The current replay uses historically recorded topic scores; full raw `as_of` re-clustering remains the next stricter validation layer.
- Point-in-time subscriber counts were not historically snapshotted, so historical channel-size stratification is not yet valid.
