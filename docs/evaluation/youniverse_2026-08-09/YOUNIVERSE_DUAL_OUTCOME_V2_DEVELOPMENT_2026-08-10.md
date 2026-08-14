# EarlySignal dual-outcome probability replay

**Development verdict:** `FAIL`  
**Train episodes:** 130  
**Temporal test episodes:** 47  
**Boundary:** development temporal test; the 2019 partition is not a new blind holdout.

| Head | Verdict | Positives | Base rate | Precision@top-20% | Lift | AP | Brier | Lead |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| adoption | INSUFFICIENT_OUTCOME_SUPPORT | 3 | 0.06383 | 0.2 | 3.133333 | 0.184722 | 0.076306 | 26.0 |
| performance | INSUFFICIENT_OUTCOME_SUPPORT | 17 | 0.653846 | 0.666667 | 1.019608 | 0.66483 | 0.244711 | 18.0 |

## Interpretation

The adoption and performance heads are intentionally independent. A passing global head still cannot issue `Act`: channel opportunity and a fresh untouched future cohort remain required.

## Reproducibility

- Protocol: `YOUNIVERSE_DUAL_OUTCOME_V2_PROTOCOL_2026-08-10.md`
- Replay: `youniverse-dual-outcome-probability-replay-v1`
- Taxonomy: `microtopic-clustering-v7.1-format-neutral-historical-ai`
- Input hash: `012e20280c2cc6a5aa5b92e3176de3fff2675b66397c592774a39b9f8b9466ce`
- Code/protocol hash: `b07e5c98dce26623dd2b422c4a5fc941d32702570800c86dcc3cd48a87802d9c`

## Adoption gate

| Check | Result |
|---|---|
| positive_support | FAIL |
| lift_at_top_quintile | PASS |
| average_precision_beats_base_rate | PASS |
| brier_beats_constant | FAIL |
| calibration_error | PASS |
| median_lead | PASS |
| not_worse_than_simple_rankings | PASS |

## Performance gate

| Check | Result |
|---|---|
| positive_support | FAIL |
| lift_at_top_quintile | FAIL |
| average_precision_beats_base_rate | PASS |
| brier_beats_constant | FAIL |
| calibration_error | PASS |
| median_lead | PASS |
| not_worse_than_simple_rankings | FAIL |
