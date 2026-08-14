# EarlySignal temporal backtest report

**Run:** production temporal baseline
**Quality gate:** INSUFFICIENT DATA
**Checkpoint count:** 1
**Precision@10:** N/A — no predictions have complete follow-up
**Median lead time:** N/A — no fired outcomes with complete follow-up
**Recall:** N/A — no fired outcomes are evaluable yet
**Evaluated prediction coverage:** 0.0%

## Gate checks

| Check | Actual | Required | Result |
|---|---:|---:|---|
| checkpoint_count | 1 | 6 | FAIL |
| evaluation_coverage_percent | 0.0 | 80 | FAIL |
| median_lead_time_days | 0.0 | 21 | FAIL |
| precision_at_k_percent | 0.0 | 40 | FAIL |

## Checkpoints

- `231b7119-d4e6-580c-a582-3e85d0cdc7a7`

## Method and limitations

- Predictions use only the latest recorded topic snapshot at or before each cutoff.
- Outcome labels are computed blindly: the labeler never reads prediction ranks or scores.
- A positive outcome requires supply growth ≥3x and median outlier lift ≥3 within the configured horizon.
- A negative is evaluated only when follow-up evidence reaches the end of the horizon; incomplete histories are excluded.
- The current replay reuses the score recorded by production at the historical timestamp. Full raw re-clustering remains a separate, stricter validation layer.

