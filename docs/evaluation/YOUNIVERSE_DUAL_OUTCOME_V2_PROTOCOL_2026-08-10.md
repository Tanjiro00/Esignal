# YouNiverse dual-outcome probability replay v2

## Purpose

This development replay replaces the unsupported conjunctive outcome from v1
with two independently testable questions:

1. Will a topic spread to additional independent creators during the following
   42 days?
2. Will future videos in the topic outperform age-matched history from their
   own channels?

It does not evaluate channel fit and cannot authorize an `Act` decision.

## Candidate universe

The research universe is created before any EarlySignal score or probability is
applied. At a weekly checkpoint a topic episode requires:

- at least 2 active videos from at least 2 channels;
- at least 1 video in the latest 7 days;
- no more than 60 active videos;
- specificity at least 70 and thesis support at least 0.8;
- a 42-day cooldown between episodes of the same stable topic identity.

The production publication gate remains separate and stricter.

## Frozen outcomes

Adoption breakout requires, within 42 days:

- at least 4 future videos;
- future supply at least 1.25 times the topic's preceding supply baseline;
- at least 2 previously unseen channels;
- at least 40% of future videos from previously unseen channels.

The preceding-supply expectation extrapolates the previous 28 days to 42 days
with a floor of 2 videos. This avoids treating a genuinely new topic as though
it already had a mature six-video baseline.

Performance breakout is evaluated only with at least 2 future videos and at
least 60% channel-baseline coverage. It requires:

- at least one future video at 2 times its channel/age baseline;
- median covered future-video performance at least 1.25 times baseline.

These labels are reported separately. Their conjunction is diagnostic only.

## Model and temporal isolation

- Final engagement is absent from candidate features.
- The first 75% of train episodes fit a regularized logistic model.
- The final 25% of train episodes is reserved for Platt calibration.
- Model parameters and calibration are frozen before the 2019 temporal split is
  scored.
- The old v1 holdout has already been inspected, so this is a development
  temporal test rather than a new blind confirmatory holdout.

## Metrics and gate

Each head reports positive support, base rate, precision and lift in the global
top quintile of the temporal test, average precision, Brier score,
constant-prevalence Brier baseline, calibration error and median lead time. A
global fraction is used because this historical taxonomy frequently contains
fewer than five eligible topics in a week; selecting five per week would then
select the full candidate universe and make lift mathematically meaningless.

A head passes the development gate only if:

- the temporal test contains at least 20 positive episodes;
- lift at five is at least 1.5;
- average precision beats the base rate;
- Brier score beats the constant-prevalence baseline;
- expected calibration error is at most 0.15;
- median lead time among selected positives is at least 7 days.

No product score weights or `Act` policy may be changed from this development
test alone. A new untouched future cohort is required for confirmation.
