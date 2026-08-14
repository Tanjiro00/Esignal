# Semantic microtrend adoption development replay

**Verdict:** `FAIL`  
**Train episodes:** 270 (37 positives)  
**Test episodes:** 287 (106 positives)  
**Boundary:** selection-biased development cohort; never a blind product claim.

| Ranking | Precision | Recall | Lift | Median lead days |
|---|---:|---:|---:|---:|
| probability_model | 0.827586 | 0.45283 | 2.240729 | 18.358 |
| recent_supply | 0.413793 | 0.226415 | 1.120364 | 21.237 |
| acceleration | 0.37931 | 0.207547 | 1.027001 | 22.349 |
| creator_breadth | 0.568966 | 0.311321 | 1.540501 | 21.76 |
| semantic_cohesion | 0.689655 | 0.377358 | 1.867274 | 22.313 |

## Probability quality

- Base rate: `0.369338`
- Average precision: `0.817906`
- Brier / constant Brier: `0.167518` / `0.232927`
- Expected calibration error: `0.157727`
- Topic bootstrap lift 95%: `{'resamples': 500, 'lower': 1.928989, 'median': 2.226724, 'upper': 2.553949}`

## Gate

| Check | Result |
|---|---|
| positive_support | PASS |
| lift_at_top_quintile | PASS |
| average_precision_beats_base_rate | PASS |
| brier_beats_constant | PASS |
| calibration_error | FAIL |
| median_lead | PASS |
| not_worse_than_simple_rankings | PASS |

## Reproducibility

- Cohort SHA-256: `33d2950fcf1a980ed1d405132e450be56e776d413c443bd569e11671be327aff`
- Embeddings SHA-256: `effe29f799cf02756c0957d6aa51adcc016d21727a58b0155685790f3f565bd0`
- Protocol SHA-256: `16eefeb8a00e0542e80012c769a36dad6286aaea5c0129a975f25afb34c6d642`
- Replay: `semantic-adoption-replay-v1`

