# EarlySignal YouNiverse structural historical replay

**Split:** `holdout`  
**Verdict:** `INSUFFICIENT_OUTCOME_SUPPORT`  
**Protocol:** `youniverse-structural-replay-v1.1-filtered-schema`  
**Outcome:** `future-topic-supply-channel-outlier-42d-v1`  
**Taxonomy:** `microtopic-clustering-v7.1-format-neutral-historical-ai`

- AI/tech videos in split artifact: 11482
- Stable topic identities: 112
- Weekly checkpoints: 36
- Deduplicated eligible episodes: 8
- Positive future outcomes: 0
- Candidate base rate: 0.0

## Ranking comparison

| Ranking | Predictions | Fired | Precision@10 | Recall | Median lead | Episode coverage | Video coverage |
|---|---:|---:|---:|---:|---:|---:|---:|
| method | 8 | 0 | 0.0 | None | None | 87.5 | 94.44 |
| supply | 8 | 0 | 0.0 | None | None | 87.5 | 94.44 |
| acceleration | 8 | 0 | 0.0 | None | None | 87.5 | 94.44 |
| channels | 8 | 0 | 0.0 | None | None | 87.5 | 94.44 |
| random | 8 | 0 | 0.0 | None | None | 87.5 | 94.44 |

## Frozen gate

| Check | Result |
|---|---|
| holdout_split | PASS |
| positive_outcome_support | FAIL |
| precision_at_10 | FAIL |
| median_lead | FAIL |
| beats_base_rate | FAIL |
| not_worse_than_each_simple_baseline | PASS |
| outcome_baseline_coverage | PASS |
| future_video_baseline_coverage | PASS |
| complete_followup | PASS |

## Method predictions

### 2019-02-24T23:59:59+00:00

Candidates: 1; positives: 0

| Rank | Topic | Score | Channels | Example stored evidence | Fired | Lead |
|---:|---|---:|---:|---|---|---:|
| 1 | PyTorch creator activity | 8.3 | 5 | [Walkthrough: Mixed Precision Training of GNMT with PyTorch](https://www.youtube.com/watch?v=Dkzp05cpdpw) | no | None |

### 2019-03-03T23:59:59+00:00

Candidates: 1; positives: 0

| Rank | Topic | Score | Channels | Example stored evidence | Fired | Lead |
|---:|---|---:|---:|---|---|---:|
| 1 | OpenAI creator activity | 13.1 | 5 | [OpenAI Text Generator](https://www.youtube.com/watch?v=0n95f-eqZdw) | no | None |

### 2019-04-14T23:59:59+00:00

Candidates: 1; positives: 0

| Rank | Topic | Score | Channels | Example stored evidence | Fired | Lead |
|---:|---|---:|---:|---|---|---:|
| 1 | TensorFlow creator activity | 12.6 | 7 | [Lab Demo - Explore & Visualize Datasets - Machine Learning with Tensorflow from Google Cloud #11](https://www.youtube.com/watch?v=yQsR4cyrpcs) | no | None |

### 2019-04-28T23:59:59+00:00

Candidates: 1; positives: 0

| Rank | Topic | Score | Channels | Example stored evidence | Fired | Lead |
|---:|---|---:|---:|---|---|---:|
| 1 | OpenAI creator activity | 14.2 | 6 | [How to beat the OpenAI \| Position 6 Highlights](https://www.youtube.com/watch?v=Jz_uZ7oIneg) | no | None |

### 2019-05-05T23:59:59+00:00

Candidates: 1; positives: 0

| Rank | Topic | Score | Channels | Example stored evidence | Fired | Lead |
|---:|---|---:|---:|---|---|---:|
| 1 | TensorFlow 2 creator activity | 12.5 | 5 | [Python Neural Networks - Tensorflow 2.0 Tutorial - Creating a Model](https://www.youtube.com/watch?v=cvNtZqphr6A) | no | None |

### 2019-05-12T23:59:59+00:00

Candidates: 1; positives: 0

| Rank | Topic | Score | Channels | Example stored evidence | Fired | Lead |
|---:|---|---:|---:|---|---|---:|
| 1 | TensorFlow practical implementations | 11.0 | 5 | [Build an AI-powered Pet Detector with Python TensorFlow and Visual Studio Code - BRK3014](https://www.youtube.com/watch?v=Oi3Hn_UtDEw) | no | None |

### 2019-05-26T23:59:59+00:00

Candidates: 1; positives: 0

| Rank | Topic | Score | Channels | Example stored evidence | Fired | Lead |
|---:|---|---:|---:|---|---|---:|
| 1 | TensorFlow creator activity | 8.8 | 7 | [Building Cross-Cloud ML Pipelines with Kubeflow with Spark & Tensorflow - Holden Karau](https://www.youtube.com/watch?v=jdBbFSghM2s) | no | None |

### 2019-08-04T23:59:59+00:00

Candidates: 1; positives: 0

| Rank | Topic | Score | Channels | Example stored evidence | Fired | Lead |
|---:|---|---:|---:|---|---|---:|
| 1 | PyTorch creator activity | 11.5 | 5 | [PyTorch Skills: Building Your First PyTorch Solution Course Preview](https://www.youtube.com/watch?v=K7Y-sCVh2ws) | no | None |

## False positives

| Checkpoint | Topic | Example stored evidence | Future supply growth |
|---|---|---|---:|
| 2019-02-24T23:59:59+00:00 | PyTorch creator activity | [Walkthrough: Mixed Precision Training of GNMT with PyTorch](https://www.youtube.com/watch?v=Dkzp05cpdpw) | 0.314 |
| 2019-03-03T23:59:59+00:00 | OpenAI creator activity | [OpenAI Text Generator](https://www.youtube.com/watch?v=0n95f-eqZdw) | 0.267 |
| 2019-04-14T23:59:59+00:00 | TensorFlow creator activity | [Lab Demo - Explore & Visualize Datasets - Machine Learning with Tensorflow from Google Cloud #11](https://www.youtube.com/watch?v=yQsR4cyrpcs) | 0.5 |
| 2019-04-28T23:59:59+00:00 | OpenAI creator activity | [How to beat the OpenAI \| Position 6 Highlights](https://www.youtube.com/watch?v=Jz_uZ7oIneg) | 0.0 |
| 2019-05-05T23:59:59+00:00 | TensorFlow 2 creator activity | [Python Neural Networks - Tensorflow 2.0 Tutorial - Creating a Model](https://www.youtube.com/watch?v=cvNtZqphr6A) | 1.467 |
| 2019-05-12T23:59:59+00:00 | TensorFlow practical implementations | [Build an AI-powered Pet Detector with Python TensorFlow and Visual Studio Code - BRK3014](https://www.youtube.com/watch?v=Oi3Hn_UtDEw) | 0.167 |
| 2019-05-26T23:59:59+00:00 | TensorFlow creator activity | [Building Cross-Cloud ML Pipelines with Kubeflow with Spark & Tensorflow - Holden Karau](https://www.youtube.com/watch?v=jdBbFSghM2s) | 0.8 |
| 2019-08-04T23:59:59+00:00 | PyTorch creator activity | [PyTorch Skills: Building Your First PyTorch Solution Course Preview](https://www.youtube.com/watch?v=K7Y-sCVh2ws) | 0.667 |

## Positive episodes missed by the method

| Checkpoint | Topic | Example stored evidence | Future supply growth |
|---|---|---|---:|
| — | None | — | — |

## Reproducibility

- AI artifact SHA-256: `b6d2520083c7f2f217855cdcaa0caea1b94aa1b87a7903db7b36a10021777f63`
- Baseline artifact SHA-256: `aa221032bd24b8cde82b545e95347e8ee495257fce5c19e4ec9384683743f6cb`
- Channel time-series SHA-256: `1c837ad5ae378bb06d5e5927278fb6b8e9056fd4dfbf46af42782cb439e2293d`
- Code/protocol SHA-256: `e65589464d4bbb4d233651cca09be7ec139930dca973e2d2ffe78dc655553904`
- Preregistration: `YOUNIVERSE_STRUCTURAL_BACKTEST_PREREGISTRATION_2026-08-09.md`
- Source: https://doi.org/10.5281/zenodo.4650046

## Interpretation boundary

Final video engagement is used only by the future outcome evaluator. The candidate generator receives no final per-video views, likes or dislikes.

This evaluates the metadata-only structural slice inside the YouNiverse channel frame, not the full production stack or all of YouTube.
