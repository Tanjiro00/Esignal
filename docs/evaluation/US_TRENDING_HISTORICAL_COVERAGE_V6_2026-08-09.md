# EarlySignal US Trending v6 historical coverage and wave replay

**Taxonomy coverage: PASS. Predictive validation: NOT ESTABLISHED.**

- Archive videos: 47142
- Daily snapshots: 264717
- Strict AI/tech titles that actually reached US Trending: 28
- Titles mapped to any production topic identity: 28 (100.0%)
- Visible at first Trending observation: 19 (67.9%)
- Actionable at first Trending observation: 0 (0.0%)

## Interpretation

The v6 subject/event taxonomy fixes the admission failure seen in v5: clear AI/tech titles are now mapped without treating video format as trend identity. This establishes taxonomy coverage only; it does not establish predictive power.

The fixed production evidence gate still emitted no actionable topic. The archive is sparse at the microtrend level and often contains only one publishing channel per subject/event identity. We did not weaken the three-channel corroboration rule to force a positive result.

This is a negative/indeterminate replay result, not a complete pre-trending backtest. US Trending contains only videos after selection into the chart and omits the non-trending candidate universe, so unbiased precision, false-positive rate and lead time cannot be estimated from it.

## Historical wave replay

- Observed checkpoints across admitted mapped videos: 146
- Checkpoints with at least one visible topic: 116
- Checkpoints with at least one actionable topic: 0
- Topic identities ever actionable: 0
- Maximum visible topics at one checkpoint: 4
- Maximum videos in one visible identity: 2
- Maximum distinct channels in one visible identity: 2

## Audited videos

| First trending | Title | Mapped | Visible | Actionable | Topic |
|---|---|---|---|---|---|
| 2021-02-24 | I asked an AI for video ideas, and they were actually good | yes | no | no |  |
| 2021-12-08 | 'Tesla as the World’s Biggest Robot Company:' Elon Musk on AI and U.S. Innovation \| WSJ | yes | no | no |  |
| 2022-06-21 | Did Google’s A.I. Just Become Sentient? Two Employees Think So. | yes | yes | no | Google AI sentience claims concerns |
| 2022-07-10 | Summoning Thor's Hammer! (with A.I.) | yes | no | no |  |
| 2022-10-02 | Optimus Robot Revealed at Tesla AI Day | yes | yes | no | Optimus product and capability release |
| 2022-12-17 | It’s Time to Pay Attention to A.I. (ChatGPT and Beyond) | yes | no | no |  |
| 2022-12-22 | AI learns to WALK 3D (Part 2) | yes | yes | no | AI robotics robot capability |
| 2023-01-27 | A.I. Versus The Law | yes | yes | no | Artificial intelligence legal and regulatory scrutiny |
| 2023-02-07 | Google Panics Over ChatGPT [The AI Wars Have Begun] | yes | yes | no | Google–ChatGPT competitive response |
| 2023-02-11 | Google Embarrass Themselves (A.I. War Is Heating Up) | yes | yes | no | Google–ChatGPT competitive response |
| 2023-02-15 | I tried using AI. It scared me. | yes | yes | no | Artificial intelligence reliability and safety concerns |
| 2023-02-22 | ChatGPT Has A Serious Problem | yes | yes | no | ChatGPT reliability and safety concerns |
| 2023-02-26 | AI Learns to Play DONKEY KONG | yes | yes | no | Artificial intelligence new model capability |
| 2023-03-16 | GPT-4 Developer Livestream | yes | yes | no | GPT-4 product and capability release |
| 2023-03-17 | Introducing Microsoft 365 Copilot \| Your Copilot for Work | yes | yes | no | Microsoft 365 Copilot product and capability release |
| 2023-03-29 | AI is Evolving Faster Than You Think [GPT-4 and beyond] | yes | yes | no | GPT-4 product and capability release |
| 2023-04-02 | Making a SECRET Glow-in-the-Dark Garden (because AI told us to) | yes | no | no |  |
| 2023-05-20 | Elon Musk on Sam Altman and ChatGPT: I am the reason OpenAI exists | yes | no | no |  |
| 2023-06-17 | ChatGPT Explained Completely. | yes | no | no |  |
| 2023-06-23 | Did AI Prove Our Proton Model WRONG? | yes | yes | no | Artificial intelligence new model capability |
| 2023-11-07 | OpenAI DevDay, Opening Keynote | yes | yes | no | OpenAI product and capability release |
| 2023-11-28 | The Entire OpenAI Chaos Explained | yes | yes | no | OpenAI governance change |
| 2023-12-07 | Hands-on with Gemini: Interacting with multimodal AI | yes | yes | no | Gemini product and capability release |
| 2023-12-08 | Gemini: Google’s newest and most capable AI model | yes | yes | no | Gemini product and capability release |
| 2024-01-18 | Samsung S24 Ultra Hands On - Galaxy AI is CRAZY! | yes | no | no |  |
| 2024-03-20 | Nvidia 2024 AI Event: Everything Revealed in 16 Minutes | yes | yes | no | NVIDIA product and capability release |
| 2024-03-26 | The Race For AI Robots Just Got Real (OpenAI, NVIDIA and more) | yes | yes | no | AI robotics capability race |
| 2024-04-11 | The Artificial Intelligence Rice Cooker. | yes | no | no |  |

## Reproducibility

- Dataset SHA-256: `09f25753a4d447e3169f964a6a09e6d96a3653b354cab1d569abf21e9d9a7f51`
- Archive adapter: `kaggle-rsrishav-us-v1346`
- Replay core: `external-youtube-timeseries-replay-v3-v6-taxonomy`
- Source: https://www.kaggle.com/datasets/rsrishav/youtube-trending-video-dataset
- License: CC0 (as declared by the dataset publisher)
