# EarlySignal Slice 6 — initial manual-evaluation report

- Evaluation set: `manual-topic-labels-v1`
- Captured: 2026-07-20
- Topics: 100
- Reviewer identity: `expert-fixture-panel-v1`
- Baseline: `live-microtopic-clustering-v4`
- Current candidate: `microtopic-clustering-v5`
- Dataset SHA-256:
  `b0145963a5050d7a73a9dd6abb5c527f7e02715e8509425b67855acb90707a6a`

## Dataset contract

The committed JSONL contains 100 curated regression scenarios, ten for each
primary label:

- true early signal;
- true but late;
- weak signal;
- false signal;
- too broad;
- too narrow;
- duplicate;
- saturated;
- declining;
- insufficient evidence.

Every row freezes its `as_of` time, three evidence IDs, the measurement time,
reviewer, notes, and baseline/current model versions. The fixture explicitly
states that future measurements are excluded. It never writes to production
tables and is not used to tune weights automatically.

## Initial comparison

| Metric | v4 baseline | v5 candidate |
| --- | ---: | ---: |
| Visible candidates | 90 | 16 |
| Precision | 11.1% | 62.5% |
| Recall on reviewed candidate universe | 100.0% | 100.0% |
| Precision@3 | 0.0% | 62.5% |
| Late-signal rate | 11.1% | 0.0% |
| False-positive rate | 77.8% | 37.5% |

Cross-cutting labels in the fixture:

- topic split error scenarios: 30/100;
- demand-relevant scenarios: 70/100;
- opportunity-actionable scenarios: 20/100.

## Interpretation

This is a deterministic regression fixture, not a claim about live market
accuracy. Its purpose is to catch known broad-topic, late-signal, duplicate,
demand, and generic-opportunity regressions before deployment. Live precision
and recall must be reported separately from labels created in the admin
evaluation queue.

The candidate is deliberately more conservative: it preserves every known
true-early scenario while suppressing most known false-positive families. Six
weak/broad cases remain visible so the report does not encode a perfect result.

## Next review

Export live labels from `/api/v1/admin/evaluation/export` or
`scripts/export_manual_evaluation.py`. Re-run the comparison after at least 100
real point-in-time reviews, report confidence intervals, and keep model-weight
changes behind an explicit reviewed release.
