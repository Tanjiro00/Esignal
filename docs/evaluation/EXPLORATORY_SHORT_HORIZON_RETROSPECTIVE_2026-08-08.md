# EarlySignal exploratory short-horizon retrospective

- Protocol: `exploratory-short-horizon-retrospective-v1`
- Cohort: `a51029e6-52cc-5cc1-b227-332d5b59c439`
- Dataset hash: `3d6015b6fd96e4d6543a2539f43db447ee640a4530d0b9cff9265127c55b8b48`
- Evaluation cutoff: `2026-08-08T08:38:51.047697+00:00`
- Split: **train only**
- Holdout opened: **no**
- Formal 42-day quality gate: **not run**

## Result

| Horizon | Mature checkpoints | Frozen predictions | Evaluable | Coverage | Fired | Precision@10 | Median lead |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1d | 6 | 60 | 27 | 45.0% | 0 | 0.0% | N/A |
| 3d | 5 | 50 | 22 | 44.0% | 0 | 0.0% | N/A |
| 5d | 3 | 30 | 13 | 43.3% | 0 | 0.0% | N/A |

The short-window result does not support a quality claim. No frozen top-10 prediction jointly reached 3x supply growth and 3x median outlier lift. Coverage is also below the registered 80% minimum because many topic IDs have no follow-up observation near the end of the window.

## Interpretation

1. This is a real retrospective calculation over observations stored after each checkpoint; missing follow-up is excluded rather than counted as a miss.
2. The 1/3/5-day check is diagnostic. The implementation plan's official gate remains precision@10 >= 40% and median lead time >= 21 days over a complete 42-day window.
3. Current labels are included only for readability and were not used by the evaluator. The stable candidate key and snapshot IDs are the evidence keys.
4. Recall is intentionally not reported in this optimized top-k pass. It must be computed over the full candidate universe by the blind 42-day run.

## Diagnostic findings

### 1-day horizon

- Any follow-up: 27/60
- Evaluable: 27/60 (45.0%)
- Supply gate reached separately: 0
- Lift gate reached separately: 1
- Joint firing: 0

| Checkpoint | Follow-up | Evaluable | Fired | Precision |
|---|---:|---:|---:|---:|
| `2026-07-31T23:59:11.057367+00:00` | 4/10 | 4 | 0 | 0.0% |
| `2026-08-01T23:59:05.627851+00:00` | 2/10 | 2 | 0 | 0.0% |
| `2026-08-02T23:59:18.887888+00:00` | 4/10 | 4 | 0 | 0.0% |
| `2026-08-03T23:56:37.028905+00:00` | 4/10 | 4 | 0 | 0.0% |
| `2026-08-04T23:58:33.508059+00:00` | 6/10 | 6 | 0 | 0.0% |
| `2026-08-05T23:59:14.270411+00:00` | 7/10 | 7 | 0 | 0.0% |

Closest observations to the joint gate:

| Display label (current, not scored) | Rank | Supply peak | Lift peak | Joint gate fraction | Baseline snapshot |
|---|---:|---:|---:|---:|---|
| AI subscription tool access costs | 4 | 1.5x | 2.4314x | 0.5 | `5a8de613-312e-497d-9cb5-a58f65d10f04` |
| Productivity workflows without recurring subscriptions | 9 | 1.3333x | 1.445x | 0.4444 | `b2b8b255-20a6-466b-8f75-dd8876e01f94` |
| AI coding assistants developer productivity benchmarks | 4 | 1.25x | 1.1197x | 0.3663 | `bca52171-0158-4450-bec0-9f1393090a9c` |
| AI video generation workflows without recurring subscriptions | 7 | 1.25x | 1.0941x | 0.3601 | `9d9c6001-10e5-46d4-97cb-fa501ae4bfe0` |
| cloud gaming latency benchmark | 6 | 1.0x | 3.1126x | 0.3333 | `2a0838c2-236b-4569-ab1e-7acc3144951d` |

### 3-day horizon

- Any follow-up: 24/50
- Evaluable: 22/50 (44.0%)
- Supply gate reached separately: 0
- Lift gate reached separately: 1
- Joint firing: 0

| Checkpoint | Follow-up | Evaluable | Fired | Precision |
|---|---:|---:|---:|---:|
| `2026-07-31T23:59:11.057367+00:00` | 5/10 | 5 | 0 | 0.0% |
| `2026-08-01T23:59:05.627851+00:00` | 4/10 | 3 | 0 | 0.0% |
| `2026-08-02T23:59:18.887888+00:00` | 4/10 | 3 | 0 | 0.0% |
| `2026-08-03T23:56:37.028905+00:00` | 4/10 | 4 | 0 | 0.0% |
| `2026-08-04T23:58:33.508059+00:00` | 7/10 | 7 | 0 | 0.0% |

Closest observations to the joint gate:

| Display label (current, not scored) | Rank | Supply peak | Lift peak | Joint gate fraction | Baseline snapshot |
|---|---:|---:|---:|---:|---|
| Developer tools: deliver a measurable practical outcome for business teams | 8 | 1.5x | 1.6667x | 0.5 | `6136ddf2-5069-40a4-9688-cdd26526b761` |
| Productivity workflows without recurring subscriptions | 9 | 1.3333x | 1.445x | 0.4444 | `b2b8b255-20a6-466b-8f75-dd8876e01f94` |
| AI coding assistants developer productivity benchmarks | 7 | 1.25x | 1.1984x | 0.3991 | `2f4e892f-d5c1-429d-adba-c650c3a91aab` |
| AI coding assistants developer productivity benchmarks | 4 | 1.25x | 1.1758x | 0.3663 | `bca52171-0158-4450-bec0-9f1393090a9c` |
| AI video generation workflows without recurring subscriptions | 7 | 1.25x | 1.1254x | 0.3601 | `9d9c6001-10e5-46d4-97cb-fa501ae4bfe0` |

### 5-day horizon

- Any follow-up: 16/30
- Evaluable: 13/30 (43.3%)
- Supply gate reached separately: 1
- Lift gate reached separately: 0
- Joint firing: 0

| Checkpoint | Follow-up | Evaluable | Fired | Precision |
|---|---:|---:|---:|---:|
| `2026-07-31T23:59:11.057367+00:00` | 5/10 | 4 | 0 | 0.0% |
| `2026-08-01T23:59:05.627851+00:00` | 4/10 | 3 | 0 | 0.0% |
| `2026-08-02T23:59:18.887888+00:00` | 7/10 | 6 | 0 | 0.0% |

Closest observations to the joint gate:

| Display label (current, not scored) | Rank | Supply peak | Lift peak | Joint gate fraction | Baseline snapshot |
|---|---:|---:|---:|---:|---|
| Free, local and unlimited AI video generation | 6 | 3.0x | 1.4475x | 0.4825 | `c0a32db5-ead2-43d5-9011-0d1cbd531c6f` |
| AI coding assistants developer productivity benchmarks | 4 | 1.25x | 1.1984x | 0.3991 | `bca52171-0158-4450-bec0-9f1393090a9c` |
| AI video generation workflows without recurring subscriptions | 7 | 1.25x | 1.2018x | 0.3601 | `9d9c6001-10e5-46d4-97cb-fa501ae4bfe0` |
| Local and offline deployment of open AI models | 9 | 1.0x | 2.7485x | 0.3333 | `10a0b75c-b113-45ee-95da-8d516e2af78c` |
| Beginner and no-code AI agents | 1 | 1.0x | 1.3571x | 0.3333 | `4652b2ec-b791-4499-9a17-d4556a4cfcd0` |

## Required fixes before interpreting the formal gate

1. Repair topic identity continuity so a frozen candidate keeps receiving auditable follow-up snapshots across re-clustering and merges.
2. Raise evaluable coverage above 80% before treating precision as stable.
3. Diagnose why the ranking favors topics whose future supply remains flat; calibrate on train only and keep holdout sealed.
4. Run the registered blind 42-day outcome labeler when windows mature. Do not substitute this diagnostic for the quality gate.

