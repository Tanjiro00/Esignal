# EarlySignal train-only ranking calibration diagnostic

- Protocol: `train-ranking-continuous-outcome-diagnostic-v1`
- Cohort: `a51029e6-52cc-5cc1-b227-332d5b59c439`
- Dataset hash: `3d6015b6fd96e4d6543a2539f43db447ee640a4530d0b9cff9265127c55b8b48`
- Split: **train only**
- Holdout opened: **no**
- Outcome proxy: best joint fraction of the pre-registered 3x supply / 3x lift gate
- Follow-up mode: direct historical `topic_id` only

## Result

| Horizon | Predictions | Direct follow-up | Evaluable | Score Spearman | Rank 1–3 median | Rank 4–7 median | Rank 8–10 median |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1d | 60 | 27 | 27 | +0.099 | 0.333 | 0.333 | 0.333 |
| 3d | 50 | 24 | 22 | −0.168 | 0.283 | 0.333 | 0.333 |
| 5d | 30 | 16 | 13 | −0.102 | 0.333 | 0.333 | 0.333 |

The current score does not demonstrate useful short-horizon ordering on this train sample.
Higher-ranked predictions were not consistently closer to the joint outcome gate than lower-ranked
predictions.

## Descriptive component signals

These are repeated-topic, small-sample correlations. They are hypotheses for a future train
ablation, not approved weight changes.

| Component | 1d | 3d | 5d | Descriptive direction |
|---|---:|---:|---:|---|
| Transcript coverage | +0.250 | +0.387 | +0.652 | positive |
| Search appearances, 24h | +0.220 | +0.355 | +0.566 | positive |
| Top velocity share | −0.240 | −0.213 | −0.451 | concentration risk |
| Specificity | −0.128 | +0.223 | +0.627 | unstable, possibly longer-horizon positive |
| Prediction score | +0.099 | −0.168 | −0.102 | no demonstrated ordering |

## Decision

1. Do not tune deterministic scoring weights on this sample. The effective sample is only 16–27
   direct-follow-up predictions and identity churn is informative missingness.
2. Deploy immutable snapshot identity and durable topic lineage first.
3. Accumulate new point-in-time checkpoints and require at least 80% follow-up coverage before
   comparing score variants.
4. On train only, evaluate ablations for transcript coverage, repeated search appearances, and
   top-source concentration. Select a candidate only if it improves checkpoint-level precision and
   calibration, not merely row-level correlation.
5. Keep the frozen holdout sealed until the registered 42-day outcome window matures.

This diagnostic does not pass or replace the formal quality gate.
