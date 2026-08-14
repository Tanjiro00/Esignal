# Semantic microtrend adoption development replay

Protocol frozen: 2026-08-13, before inspecting any June semantic candidate,
prediction or outcome.

## Question

Can clusters formed from point-in-time semantic evidence rank concrete English
AI/technology topics that will spread to additional independent YouTube creators
during the following 42 days?

The replay evaluates topic adoption only. It does not evaluate future views,
channel fit or authorize a product `Act` decision.

## Cohort and embeddings

- The source cohort is the same public-metadata-only, selection-biased
  2026-01-01–2026-08-13 production export frozen in
  `MODERN_ADOPTION_DEVELOPMENT_PROTOCOL_2026-08-13.md`.
- A deterministic title-only v7 AI relevance filter selects 14,233 of 42,610
  videos. It does not inspect engagement or future activity.
- Each selected video is embedded independently from its format-normalized title
  and the first 400 cleaned description characters with
  `text-embedding-3-small`, reduced by the API to 256 dimensions.
- Embeddings are cached by video id and source hash. A checkpoint sees only
  videos published at or before that checkpoint; corpus-wide fitting is absent.

## Frozen candidate construction

At each checkpoint, HDBSCAN runs on normalized embeddings from the preceding 35
days using Euclidean distance, `min_cluster_size=2`, `min_samples=2` and leaf
selection. A visible candidate requires:

- 2–60 active videos;
- at least 2 independent channels;
- at least 1 video in the preceding 7 days;
- mean member-to-centroid cosine similarity at least 0.72;
- minimum member-to-centroid similarity at least 0.62.

The stable topic track is stitched between checkpoints when centroid similarity
is at least 0.84 and active members overlap with Jaccard at least 0.1. The
episode cooldown remains 42 days. Titles and presentation formats are evidence,
not part of the stable identity or deterministic score. Any later LLM label may
summarize only stored evidence and cannot change cluster membership or scores.

## Frozen future assignment and outcome

Future videos are never used to form the candidate centroid. During the next 42
days each future video may belong to at most one candidate from the frozen
checkpoint. It is assigned to the nearest candidate only when:

- cosine similarity to that candidate centroid is at least 0.74; and
- similarity to its closest stored exemplar is at least 0.78.

These radii were selected once on the March–May train partition. Wider radii
visibly combined different subjects and produced 74 future members in one
cluster; narrower radii left only 5–16 positive train outcomes. The selected
radius yielded 37 positives among 270 train episodes before the June partition
was opened.

A positive adoption outcome is unchanged from the preceding protocol:

- at least 4 assigned future videos;
- future supply at least 1.25 times the preceding 28-day rate extrapolated to 42
  days, with an expected-supply floor of 2;
- at least 2 channels absent from the matching prior 180-day topic history;
- at least 40% of assigned future videos from those new channels.

## Split, model and gate

- Train checkpoints: weekly 2026-03-01 through 2026-05-25.
- First 75% of train checkpoints fit the regularized logistic model; the last
  25% calibrate it when calibration support is sufficient.
- Development test: weekly 2026-06-01 through 2026-07-02, with a complete 42-day
  outcome window.
- Features contain only checkpoint-time supply, acceleration, creator breadth
  and entropy, topic age and semantic cohesion.
- Baselines are recent supply, acceleration, creator breadth and semantic
  cohesion on exactly the same episodes.

Directional gate:

- at least 20 positive test episodes;
- top-quintile lift at least 1.5;
- average precision above base rate;
- Brier score below a constant-prevalence forecast;
- expected calibration error at most 0.15;
- median lead at least 7 days;
- top-quintile precision no worse than every simple baseline.

Even a full pass is only a development result because the monitored-channel
universe was assembled using current information. It can authorize a fresh
prospective cohort, never a production probability or weight change by itself.
