# EarlySignal global cross-market historical replay preregistration

**Frozen at:** 2026-08-09, before reading or aggregating the global archive.  
**Dataset:** Global YouTube Trending Dataset 2022–2025, Illinois Data Bank,
`10.13012/B2IDB-9307654_V1`.  
**Taxonomy:** `microtopic-clustering-v6-subject-event`.  
**Status:** FROZEN — outcome thresholds and the holdout boundary must not be changed
after the filtered archive is opened.

**Pre-outcome amendment, 2026-08-09:** a partial extraction diagnostic exposed that
the original ASCII fallback admitted titles explicitly labelled `fr`/`it` (for
example, the French contraction `j'ai` also triggered the token `ai`) and that the
case-insensitive standalone token `ai` matched an unrelated Albanian word. Before
any train or holdout outcome was calculated, admission was tightened so an explicit
non-English language code always wins over the fallback and standalone AI must be
uppercase/dotted; named products and phrases remain case-insensitive. No score,
candidate, outcome, split or gate threshold changed.

**Pre-outcome amendment 2, 2026-08-09:** a protocol review before outcome processing
found that weekly checkpoints could count one still-unresolved topic several times.
The first eligible checkpoint now starts a 21-day opportunity episode; repeats of
the same topic identity inside that window are suppressed for the method and every
baseline. This changes neither ranking scores nor outcome thresholds and prevents
pseudo-replication from inflating sample size.

## Question

Can the deterministic EarlySignal method, using only information available at a
historical checkpoint, rank English-language AI/technology subject/event topics
that later spread across additional videos, independent channels and national
Trending markets?

This is a test of cross-market diffusion after the first platform-curated Trending
appearance. It is not a claim that the method detects a topic before any YouTube
Trending confirmation, because the dataset does not contain that earlier candidate
universe.

## Immutable data boundary

- Source period: 2022-07-01 through 2025-06-30.
- Four public Trending retrievals per day across 104 countries.
- English admission requires an English language field. The ASCII-letter fallback
  (at least 80% in the title) is used only when both language fields are empty; an
  explicit non-English language code always rejects the row.
- Vertical admission uses the token-aware AI/technology matcher; raw substring
  matching for `ai` is prohibited.
- Canonical deduplication uses YouTube `video_id`; independent publication evidence
  uses `channel_id`.
- A feature at checkpoint `t0` may use only rows with `collection_date <= t0` and
  videos with `published_at <= t0`.
- Future rows are available only to the blind outcome pass.

## Temporal split

- Train: 2022-07-01 through 2024-06-30.
- Holdout: 2024-07-01 through 2025-06-30.
- Weekly checkpoints are Sundays at 23:59:59 UTC after a 30-day warm-up.
- The holdout may be opened once, after the train report and code hash are saved.

The taxonomy code was developed before this preregistration and is therefore not a
blind model. Only the final temporal holdout is treated as blind outcome evidence.

## Candidate construction at `t0`

1. Build v6 subject/event identities from titles, descriptions and normalized named
   products available at `t0`.
2. Exclude format, hook, audience and creator angle from the identity key.
3. Keep the production-visible topic floor: specificity at least 70 and thesis
   support at least 0.8.
4. The method may emit a prediction only with at least three distinct videos from
   three distinct channels inside the 30-day lookback and at least two of those
   channels observed during the last seven days.
5. Rank eligible topics using the deterministic production score. Select top 10 per
   checkpoint. No LLM may change score, rank or outcome.
6. Treat the first eligible checkpoint as one opportunity episode and suppress the
   same topic identity for the following 21 days. This prevents adjacent weekly
   checkpoints from inflating sample support with the same unresolved event.

## Frozen cross-market outcome

A predicted topic fires inside the following 21 days only when all conditions become
true at the same future observation:

1. Rolling seven-day distinct-video supply is at least 3x the `t0` supply and adds at
   least three new independent channels.
2. Country breadth adds at least five new countries and reaches at least eight total
   countries.
3. At least half of the future distinct videos were not present at `t0`.
4. The event occurs at least 24 hours after `t0`; same-snapshot global duplication is
   not counted as a prediction.

Lead time is measured from `t0` to the first observation satisfying all four
conditions. View-count lift is retained as a secondary diagnostic, not as a label,
because Trending snapshots do not provide an unbiased channel-age baseline for the
complete non-Trending upload universe.

## Frozen baselines

- Current seven-day distinct-video supply.
- Current country breadth.
- Current aggregate view velocity.
- Median per-video view growth while on Trending.
- Deterministic seeded random ranking over the same visible candidates.

Every baseline selects the same top-k and is evaluated on the same outcome map.

## Primary metrics and product gate

- Precision@10 and recall over fired visible candidates.
- Median lead time.
- Predictions and positives per checkpoint.
- False-positive rate across matured predictions.
- Lift over candidate base rate and each simple baseline.
- Results reported separately for train, holdout and all checkpoints.

The cross-market test passes only if the holdout contains at least 20 positive topic
outcomes and all of the following hold:

- precision@10 at least 40%;
- median lead time at least seven days;
- precision exceeds candidate base rate;
- precision is not worse than every simple baseline;
- at least 80% of predictions have complete 21-day follow-up.

If the holdout has fewer than 20 positives, the result is `INSUFFICIENT OUTCOME
SUPPORT`, never `PASS`. Zero predictions produce undefined precision (`N/A`), not
0%.

## Robustness checks fixed in advance

- Recompute descriptive sensitivity only, without changing the primary verdict, for
  country-growth floors of 3 and 10 and horizons of 14 and 30 days.
- Report duplicate-video country spread separately from new-video/new-channel spread.
- Report product/event identities with the largest false-positive contribution.
- Verify that removing title format markers does not change topic identity.

## Required artifacts

- Source file SHA-256 and filtered-slice SHA-256.
- Streaming filter counts and rejection reasons.
- Frozen train predictions before holdout opening.
- Train, holdout and combined JSON/Markdown reports.
- Topic-level evidence rows resolving every prediction and outcome.
- Exact code and protocol versions.
