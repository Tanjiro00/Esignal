# Semantic adoption — prospective shadow protocol

Protocol frozen: 2026-08-13, before generating or inspecting the 2026-08-12
candidate set. The future outcome window is unavailable at freeze time.

## Purpose and boundary

This run asks whether point-in-time semantic candidates can rank English
AI/technology topics that subsequently spread to additional independent YouTube
creators. It evaluates cross-creator adoption, not future views or the expected
performance of a particular creator's video.

The run is shadow-only. It cannot create a product `Act`, change production
scores, show a viral probability, or make a marketing claim.

## Frozen inputs

- Candidate checkpoint: `2026-08-12T23:59:59Z`.
- Freeze date: `2026-08-13`.
- First permitted outcome opening: `2026-09-24`.
- Candidate universe: the production monitoring universe exported on
  `2026-08-13`, with its selection bias recorded in the artifact.
- Candidate fields: public title, cleaned description, channel id and publish
  time only.
- Semantic vectors: the frozen `text-embedding-3-small`, 256-dimensional cache.
- The artifact records SHA-256 for the cohort, embeddings, protocol and every
  source file that determines candidates or ranking.

## Historical fitting

All complete weekly checkpoints from `2026-03-01` through `2026-06-28` are
training data for this prospective run. June is no longer treated as a holdout:
it was already opened during v1 development. No event after the candidate
checkpoint is used to fit or calibrate the model.

The regularized logistic head is fit on all complete historical episodes. Its
raw logit is used only as a monotonic internal rank. A probability is not
generated or stored because semantic adoption v1 failed its calibration gate.

## Candidate construction

Construction keeps the frozen v1 HDBSCAN and semantic-radius settings, with one
pre-registered quality change:

1. Format-normalized titles are tokenized deterministically.
2. Titles with Jaccard similarity at least `0.86` or containment at least
   `0.92` form one copy family.
3. At most the earliest video from a copy family is credited during candidate
   formation and future outcome counting.
4. A visible candidate still requires at least two remaining videos, two
   remaining channels, one recent video and the frozen semantic-cohesion gates.

The deterministic v8 `entity + concept` taxonomy is diagnostic only. The
March–May train analysis retained only 12 of 270 original episodes when it was
used as a hard gate, so it cannot silently suppress unknown products or novel
concepts. A cluster without a supported deterministic neutral label is marked
for an evidence-grounded Taxonomist; it is never shown under a generated label
without stored evidence.

## Frozen ranking and selection

Every candidate stores its checkpoint features and raw internal rank score. The
shadow prediction set is the top 20% of candidates by this score, with stable
topic-key tie-breaking. Simple comparison rankings are frozen at the same time:

- recent supply;
- acceleration;
- distinct creator breadth;
- semantic cohesion.

No candidate can be added, removed or re-ranked after the freeze.

## Frozen future assignment and positive outcome

After `2026-09-24`, future videos in the 42-day window may be assigned to at
most one frozen candidate. The frozen centroid and exemplar radii remain `0.74`
and `0.78`. Copy-family collapse runs before counting future videos.

A positive adoption outcome still requires:

- at least four independent future title families;
- at least `1.25×` expected supply, with expected-supply floor two;
- at least two channels absent from the prior topic history;
- at least 40% of credited future evidence from new channels.

## Evaluation gate

The prospective result is reported even if support is insufficient. The
directional gate requires:

- at least 20 candidates and at least 5 positive outcomes overall;
- top-quintile lift at least `1.5×` over the frozen candidate base rate;
- bootstrap 95% lower bound for topic-level lift above `1.0×`;
- median lead time at least 7 days;
- top-quintile precision no worse than every frozen simple ranking;
- manual evidence audit with no more than 10% copied-title or semantically
  incoherent candidates in the selected set.

Calibration is deliberately not part of this run because no probability is
emitted. A later probability model needs a separate pre-registered calibration
study.

