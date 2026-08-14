# EarlySignal US Trending historical coverage audit

**Verdict: FAIL as a coverage stress test; not a predictive validation.**

- Archive videos: 47142
- Daily snapshots: 264717
- Strict AI/tech titles that actually reached US Trending: 28
- Titles mapped to any production topic identity: 3 (10.7%)
- Actionable at first Trending observation: 0 (0.0%)

## Interpretation

The deployed deterministic taxonomy/actionability core does not cover most clear AI/tech videos even after those videos have entered US Trending. With zero actionable topics, this archive cannot produce a successful historical prediction for the current method.

This is a blocker and negative evidence, not a complete pre-trending backtest. The archive does not contain the non-trending candidate universe, so precision and lead time before Trending cannot be estimated from it.

## Audited videos

| First trending | Title | Mapped | Visible | Actionable | Topic |
|---|---|---|---|---|---|
| 2021-02-24 | I asked an AI for video ideas, and they were actually good | no | no | no |  |
| 2021-12-08 | 'Tesla as the World’s Biggest Robot Company:' Elon Musk on AI and U.S. Innovation \| WSJ | no | no | no |  |
| 2022-06-21 | Did Google’s A.I. Just Become Sentient? Two Employees Think So. | no | no | no |  |
| 2022-07-10 | Summoning Thor's Hammer! (with A.I.) | no | no | no |  |
| 2022-10-02 | Optimus Robot Revealed at Tesla AI Day | no | no | no |  |
| 2022-12-17 | It’s Time to Pay Attention to A.I. (ChatGPT and Beyond) | no | no | no |  |
| 2022-12-22 | AI learns to WALK 3D (Part 2) | no | no | no |  |
| 2023-01-27 | A.I. Versus The Law | no | no | no |  |
| 2023-02-07 | Google Panics Over ChatGPT [The AI Wars Have Begun] | no | no | no |  |
| 2023-02-11 | Google Embarrass Themselves (A.I. War Is Heating Up) | no | no | no |  |
| 2023-02-15 | I tried using AI. It scared me. | no | no | no |  |
| 2023-02-22 | ChatGPT Has A Serious Problem | no | no | no |  |
| 2023-02-26 | AI Learns to Play DONKEY KONG | no | no | no |  |
| 2023-03-16 | GPT-4 Developer Livestream | yes | no | no |  |
| 2023-03-17 | Introducing Microsoft 365 Copilot \| Your Copilot for Work | no | no | no |  |
| 2023-03-29 | AI is Evolving Faster Than You Think [GPT-4 and beyond] | no | no | no |  |
| 2023-04-02 | Making a SECRET Glow-in-the-Dark Garden (because AI told us to) | no | no | no |  |
| 2023-05-20 | Elon Musk on Sam Altman and ChatGPT: I am the reason OpenAI exists | no | no | no |  |
| 2023-06-17 | ChatGPT Explained Completely. | no | no | no |  |
| 2023-06-23 | Did AI Prove Our Proton Model WRONG? | no | no | no |  |
| 2023-11-07 | OpenAI DevDay, Opening Keynote | no | no | no |  |
| 2023-11-28 | The Entire OpenAI Chaos Explained | no | no | no |  |
| 2023-12-07 | Hands-on with Gemini: Interacting with multimodal AI | no | no | no |  |
| 2023-12-08 | Gemini: Google’s newest and most capable AI model | yes | yes | no | Gemini: deliver a measurable practical outcome for AI practitioners |
| 2024-01-18 | Samsung S24 Ultra Hands On - Galaxy AI is CRAZY! | no | no | no |  |
| 2024-03-20 | Nvidia 2024 AI Event: Everything Revealed in 16 Minutes | no | no | no |  |
| 2024-03-26 | The Race For AI Robots Just Got Real (OpenAI, NVIDIA and more) | yes | no | no |  |
| 2024-04-11 | The Artificial Intelligence Rice Cooker. | no | no | no |  |

## Reproducibility

- Dataset SHA-256: `09f25753a4d447e3169f964a6a09e6d96a3653b354cab1d569abf21e9d9a7f51`
- Archive adapter: `kaggle-rsrishav-us-v1346`
- Replay core: `external-youtube-timeseries-replay-v2`
- Source: https://www.kaggle.com/datasets/rsrishav/youtube-trending-video-dataset
- License: CC0 (as declared by the dataset publisher)
