# EarlySignal: global cross-market robustness report

**Primary verdict:** `INSUFFICIENT_OUTCOME_SUPPORT`  
**Primary reproduction:** `MATCH`

## Sensitivity (descriptive only)

| Configuration | Checkpoints | Candidates | Positives | Method precision | Lead |
|---|---:|---:|---:|---:|---:|
| primary_21d_country5 | 49 | 1 | 0 | 0.0% | N/A |
| horizon_14d | 49 | 1 | 0 | 0.0% | N/A |
| horizon_30d | 47 | 1 | 0 | 0.0% | N/A |
| new_country_floor_3 | 49 | 1 | 0 | 0.0% | N/A |
| new_country_floor_10 | 49 | 1 | 0 | 0.0% | N/A |

## Diagnostics

- Format-marker identity check: 17/18 unchanged (94.4%).
- Method predictions with country breadth but without enough new-video/new-channel supply: 0.

## Reproducibility

- Filtered evidence SHA-256: `6439761a16750de25d68c0b8aa1595cee66a6249e109a2e2a847392cddc8e30d`
- Primary code/protocol SHA-256: `9e3f9b57a68f4c76a51f1e5a65e91f1a14de9cc837e6b2717dbc3f5f02a1aa0a`
- Primary verdict is never changed by these sensitivity checks.
