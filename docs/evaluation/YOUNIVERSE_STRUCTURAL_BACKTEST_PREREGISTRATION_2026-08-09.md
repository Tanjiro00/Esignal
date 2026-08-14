# EarlySignal YouNiverse structural backtest preregistration

**Frozen at:** 2026-08-09, before inspecting filtered AI/tech outcomes  
**Dataset:** YouNiverse v1.1, Zenodo record `4650046`  
**Protocol:** `youniverse-structural-replay-v1`  
**Outcome:** `future-topic-supply-channel-outlier-42d-v1`  
**Taxonomy:** `microtopic-clustering-v7.1-format-neutral-historical-ai`  
**Status:** preregistered; holdout must remain unopened until the train report,
code hash and filtered-input hashes are persisted.

## Question

Given only English YouTube videos and channel measurements available at a
historical checkpoint, does the structural slice of EarlySignal rank narrow AI
topics that subsequently expand across creators and produce unusually strong
videos for those creators?

This test is designed to answer a narrower and more useful question than a
Trending replay: it contains ordinary uploads as well as successful uploads and
therefore supplies negative candidates.

## Source and immutable files

Official source: https://doi.org/10.5281/zenodo.4650046

Files used:

| File | Declared bytes | Declared MD5 | Purpose |
|---|---:|---|---|
| `yt_metadata_en.jsonl.gz` | 13 636 127 630 | `0514b2ee52ffaa2c9c27c539038feb60` | titles, descriptions, tags, upload dates, channels and final outcomes |
| `df_channels_en.tsv.gz` | 5 960 728 | `aa4d90892aeaae40089b5825c87607c8` | channel metadata |
| `df_timeseries_en.tsv.gz` | 571 058 429 | `689cf552e2a2c906ab7e41c01b2a8627` | weekly point-in-time channel views/subscribers |

The published dataset contains about 72.9 million videos from about 136 thousand
English-speaking channels. Video metadata was crawled from 2019-10-29 through
2019-11-23. Channel time series cover 2015 through September 2019.

Every downloaded source, filtered split, report and code bundle receives a
SHA-256. The published MD5 values must also match before analysis.

## Leakage boundary

The per-video `view_count`, `like_count` and `dislike_count` are final values at
the 2019 crawl, not historical snapshots. They are therefore forbidden as model
features, ranking inputs, eligibility inputs, taxonomy inputs or train-time
threshold inputs.

Allowed point-in-time inputs at checkpoint `t0`:

- title, description, tags, video ID, channel ID and upload date for videos
  uploaded on or before `t0`;
- weekly channel views, view delta, subscribers, subscriber delta and upload
  activity whose timestamp is on or before `t0`;
- deterministic features derived only from those rows.

Allowed future-only outcome inputs:

- videos uploaded after `t0` and no later than `t0 + 42 days`;
- their final crawl-time view counts;
- crawl-time view counts of comparison videos used exclusively to form an
  outcome-side channel baseline.

Final video engagement must never cross from the outcome evaluator into the
candidate generator or ranker. Tests must fail if a feature object exposes it.

## Universe admission

The base universe is the released English metadata file. A video enters the AI
slice only when its title contains at least one token-aware, unambiguous AI
anchor. Description and tags may reinforce or disambiguate a title but may not
admit a video on their own.

Frozen historical anchors include:

- `artificial intelligence`, `machine learning`, `deep learning`;
- `neural network`, `natural language processing`, `computer vision`,
  `reinforcement learning`, `generative adversarial network` or `GAN`;
- `TensorFlow`, `PyTorch`, `Keras`, `OpenAI`, `DeepMind`, `AlphaGo`, `Watson`,
  `Google Duplex`, `BERT`, `GPT-2`;
- `AI` or `A.I.` as a standalone uppercase title token;
- `AI robotics`, `self-driving AI`, `autonomous driving AI`, `chatbot AI`,
  `face recognition AI` and `AI ethics`.

Lowercase words containing `ai`, generic `robot`, generic `algorithm`, generic
`data science`, and boilerplate AI terms appearing only in a description are
rejected.

The filter reports the full funnel, accepted anchor families, years, channels,
categories and a deterministic sample of admitted/rejected rows. Admission may
be corrected on train only for demonstrable tokenization or language bugs. Any
such change must be disclosed before the holdout process reads its input.

## Format-neutral topic identity

Taxonomy v7 removes presentation markers before identity generation, including:

`tutorial`, `guide`, `review`, `explained`, `demo`, `livestream`, `podcast`,
`shorts`, `reaction`, `lecture`, `course`, `lesson`, `interview`, `keynote`,
`documentary`, `beginner`, `advanced`, `part N` and year/version boilerplate when
it is not itself the subject.

Identity is based on a canonical subject plus a substantive event/context:

- canonical product or research family, for example `TensorFlow`, `AlphaGo`,
  `BERT`, `GANs` or `neural networks`;
- substantive context, for example release, benchmark, capability, adoption,
  safety/ethics, research result, practical use or market activity.

The same subject/context must receive the same key across presentation formats.
Different products or substantive contexts must not collapse merely because
both concern AI. The taxonomy version and its synthetic invariance tests are
frozen before opening the holdout.

## Temporal split

The split is defined by upload time, not crawl time.

- Train checkpoints: weekly Sundays from `2016-01-03T23:59:59Z` through
  `2018-11-18T23:59:59Z`.
- Train maturity boundary: `2018-12-30T23:59:59Z`.
- Blind holdout checkpoints: weekly Sundays from `2019-01-06T23:59:59Z` through
  `2019-09-08T23:59:59Z`.
- Holdout maturity boundary: `2019-10-20T23:59:59Z`, at least nine days before
  the earliest documented metadata crawl.

The streaming filter writes a train artifact ending at the train maturity
boundary and a physically separate sealed holdout artifact. Train analysis must
not deserialize the holdout artifact.

## Candidate state at `t0`

For each stable topic identity:

- structural and new-channel-history lookback: 180 days;
- active supply window: 35 days;
- recent window: 7 days;
- previous comparison window: days 8–35 before `t0`;
- prior-topic history for new-channel status: 180 days;
- at least 3 videos in the last 35 days;
- at least 3 independent channels in the last 35 days;
- at least 2 videos and 2 independent channels in the recent 7 days;
- at least 2 recent channels not seen for this identity in the preceding
  180-to-8-day history;
- specificity at least 70 and thesis support at least 0.8;
- no more than 25 recent-35-day videos, to exclude already saturated waves.

A topic identity can become a new candidate episode at most once every 42 days.

## Structural method score

The production deterministic scorer is reused, but unavailable inputs are held
at explicit neutral values rather than reconstructed from future data.

Observed inputs:

- upload acceleration from recent versus previous windows;
- recent supply and total supply;
- independent creator count and concentration;
- new-creator spread;
- channel-size buckets from the last weekly subscriber observation at or before
  `t0`;
- topic age, specificity and entity count;
- provider/search appearance counts represented by admitted upload counts.

Neutral or unavailable inputs:

- per-video view velocity: `0`;
- per-video outlier ratios: `1`;
- audience demand: `0`;
- transcript coverage: `0`;
- snapshot coverage: `0`;
- per-video baseline coverage: `0`.

This result evaluates the **structural metadata-only slice**, not the entire
production stack. It may invalidate a positive product claim, but a negative
result does not isolate whether richer point-in-time engagement signals would
rescue the full system.

## Frozen future outcome

For each eligible episode, evaluate videos with the same topic identity uploaded
strictly after `t0` and no later than `t0 + 42 days`.

The topic fires only when all conditions hold:

1. Future 42-day supply is at least `3x` the expected 42-day supply implied by
   the previous 28 days, with a minimum denominator of one weekly video.
2. At least 3 future videos exist.
3. At least 3 channels not present in the topic's previous 180-day history
   publish during the future window.
4. At least 50% of future videos come from those new-to-topic channels.
5. At least 3 future videos have a channel-normalized final-view outlier ratio
   of at least `3x`.
6. Median future-video outlier ratio is at least `2x`.
7. At least 80% of future videos have an eligible channel baseline.

Outcome-side channel baseline for a video:

- same channel;
- comparison videos uploaded in the prior 365 days;
- at least 5 comparison videos;
- exposure age at crawl in the same logarithmic band:
  `0–7`, `8–14`, `15–30`, `31–60`, `61–120`, `121–240`, `241+` days;
- baseline is the median final view count of those comparison videos;
- outlier ratio is future video final views divided by `max(median, 1)`.

The first future upload date at which all supply/channel conditions can be
resolved defines `fired_at`. Lead time is `fired_at - t0`: the interval for which
the method had already committed to the topic before the structural breakout
became observable. Required lead time is at least 21 days.

## Rankings and metrics

At every checkpoint, store top 10 for:

- EarlySignal structural score;
- recent 7-day supply;
- supply acceleration;
- independent-channel spread;
- seeded random ordering.

Primary metrics:

- precision@10 across deduplicated topic episodes;
- recall among positive eligible episodes;
- median lead time;
- candidate base rate;
- lift over base rate and each simple baseline;
- outcome-baseline coverage.

Every selected prediction must resolve to stored YouTube URLs and evidence
titles. Reports must include false positives and positive episodes missed by the
method.

## Product gate

The blind holdout passes only if all are true:

- at least 20 positive eligible topic episodes exist;
- method precision@10 is at least 40%;
- median lead time is at least 21 days;
- method precision exceeds candidate base rate;
- method precision is not worse than any simple baseline;
- at least 80% of selected predictions and future videos have complete required
  follow-up/baseline coverage;
- holdout is opened only after train report and code/input hashes are stored.

If the holdout contains fewer than 20 positive episodes, formal verdict is
`INSUFFICIENT_OUTCOME_SUPPORT`, never `PASS`. If support is sufficient but any
other gate fails, verdict is `FAIL`.

## Allowed train calibration

One documented train-only iteration is allowed for:

- fixing admission false positives/negatives;
- repairing topic identity and format invariance;
- choosing one candidate-floor variant among the frozen descriptive variants
  below.

The outcome definition, holdout dates, 40% precision gate, 21-day lead gate and
minimum 20 positive episodes may not change.

Frozen descriptive candidate variants:

- minimum channels: 2, 3, 5;
- recent window: 7 or 14 days;
- saturation ceiling: 15, 25 or 40 videos;
- episode cooldown: 28, 42 or 56 days.

The primary variant remains the values stated in `Candidate state at t0` unless
it fails the following train-only feasibility rule: fewer than 50 deduplicated
eligible episodes, fewer than 50 method predictions, less than 80% complete
prediction episodes, or less than 80% baseline coverage across future videos.
An episode with no future videos has complete follow-up and no baseline
requirement. Fired labels, precision, recall and lead time may be reported for
train diagnostics but may not choose a variant.

If the primary is infeasible, evaluate this frozen fallback ladder in order and
select the first feasible row:

1. `channels=2`, `recent=7`, `ceiling=25`, `cooldown=42`;
2. `channels=3`, `recent=14`, `ceiling=25`, `cooldown=42`;
3. `channels=2`, `recent=14`, `ceiling=25`, `cooldown=42`;
4. `channels=3`, `recent=14`, `ceiling=40`, `cooldown=42`;
5. `channels=2`, `recent=14`, `ceiling=40`, `cooldown=42`.

If none is feasible, retain the primary configuration and report insufficient
feasibility. The remaining frozen values (`channels=5`, `ceiling=15`, and
cooldowns 28/56) are robustness checks only and cannot become the primary
holdout configuration. No train ranking metric may reorder this ladder.

After the primary holdout report is persisted and hashed, run one-factor
robustness checks around the selected policy: `channels=5`, `ceiling=15`,
`cooldown=28`, `cooldown=56`, the other recent-window value, the other
25/40 ceiling, and the other 2/3 minimum-channel value. These checks may assess
stability but may not replace or upgrade the frozen primary verdict.

## Interpretation boundary

YouNiverse samples English channels with more than roughly 10,000 subscribers
and more than 10 videos known to Channel Crawler/Social Blade. It is not a random
sample of all YouTube and underrepresents very small or new creators.

Final view counts have unequal exposure ages. Outcome age bands and within-channel
medians reduce but do not remove survivorship, deletion, crawl-date and exposure
bias. This replay therefore tests retrospective ranking inside the YouNiverse
channel frame. It must not be described as a universal estimate for all YouTube.

No threshold may be changed after inspecting blind holdout outcomes. Any later
method version requires a new temporal cohort or a different unopened dataset.

## Pre-outcome execution log

These operational notes were recorded before a train or holdout outcome report
was generated:

1. All three source sizes and published MD5 values matched.
2. A proposed one-pass channel-grouped optimization was rejected by a hard
   invariant check when channel `UCz7ww2uU1YpSiW25rHOAI1A` reappeared in a later
   run. Its incomplete temporary outputs were never promoted or analyzed. The
   frozen evaluation uses the conservative two-pass method: first discover
   admitted AI channels, then rescan the complete archive for their baseline
   videos.
3. `orjson==3.10.18` is loaded from an isolated evaluation-only directory to
   accelerate JSON parsing and serialization. The tested standard-library JSON
   path remains the fallback and produces the same typed records. This changes
   neither admission, taxonomy, ranking nor outcome logic.
4. The baseline-only second pass reads the canonical top-level `channel_id`
   string before deserializing a row and fully deserializes only rows belonging
   to an admitted channel. Noncanonical lines take the tested JSON fallback.
   This is an execution optimization only: selected rows still pass through the
   same typed parser and date rules.
5. Synthetic taxonomy checks found two pre-outcome canonicalization defects.
   Specialized subjects such as `AI ethics` and `AI robotics` now outrank the
   parent `artificial intelligence` anchor, and integer/dot-zero product versions
   such as `TensorFlow 2` and `TensorFlow 2.0` share one identity. The fixes and
   tests were frozen before generating a train report.
6. Channel tables preserve the released header and selected TSV rows byte for
   byte inside the recompressed artifacts. The filter locates the `channel`
   column from the header and reads only that field for membership instead of
   constructing dictionaries for every unselected row. Synthetic tests cover
   both first-column and later-column channel layouts.

## Train-only taxonomy amendment before holdout inspection

The first train report exposed demonstrable title-token collisions: 2016
astrology videos containing `Gemini`, Bengali/Indonesian uses of `gan`/`keras`,
personal-name uses of `Bert`/`Claude`, and arbitrary numbers next to `DeepMind`
were being treated as AI product evidence. The first holdout process was started
before this train audit, but its report was never opened, queried, copied or
used. Its artifacts are retained under an explicit
`INVALID_CONTAMINATED_UNREAD` name for auditability and cannot contribute to any
metric or decision.

Under the preregistered one-iteration train-only allowance, taxonomy `v7.1`
makes these semantic admission corrections:

- `Gemini` and `Claude` require Google/Anthropic or explicit AI/model context;
- bare `GAN`, `Keras`, `BERT`, `NLP`, `DeepMind` and abbreviated `AI` require technical
  context, with case-sensitive acronym checks where necessary;
- generic AI/ML/deep-learning/neural-network subjects are not visible
  microtrends even when a broad facet can be inferred;
- arbitrary adjacent numbers no longer become versions of unversioned research
  organizations such as `DeepMind`.

These changes were derived only from train evidence and synthetic semantic
tests. The candidate policy, future outcome, product gate, temporal split and
holdout data are unchanged. Taxonomy code and a replacement train report must be
hashed before the valid holdout is executed. No value from the invalid holdout
attempt may be inspected before the replacement primary holdout is frozen.

## Outcome-adapter execution amendment

The replacement holdout report showed an impossible combination: high baseline
coverage with all outlier ratios equal to zero. Inspection found a mechanical
schema-boundary defect. The streaming filter intentionally renamed raw
`view_count`, `like_count` and `dislike_count` to `final_*` to make their
outcome-only provenance explicit, while the replay adapter accepted only the raw
names and therefore parsed every filtered engagement count as zero.

That report is invalid and retained as `INVALID_ZERO_OUTCOMES`. The defect did
not affect admission, topic identity, eligibility, ranking, evidence URLs or
the frozen policy because candidate-side types do not expose any final
engagement field. The adapter now accepts both the released raw names and the
filtered provenance-preserving names, and regression tests cover both shapes.
No outcome threshold or candidate score changed.

Because the zero-outcome report was inspected during diagnosis, even a passing
replacement report must be described as retrospective/provisional rather than
an untouched confirmatory holdout. The actual nonzero outcome labels had not
been evaluated by the method before this schema fix, but a future formal `PASS`
still requires a fresh temporal cohort or different unopened dataset.
