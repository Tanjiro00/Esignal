# Modern YouTube adoption development replay

Protocol frozen: 2026-08-13, before exporting or scoring the cohort.

## Question

Can point-in-time topic structure rank English AI/technology microtopics that
will spread to additional independent YouTube creators during the following 42
days?

This replay evaluates adoption only. It does not evaluate future views, channel
fit, content gaps or authorize a product `Act` decision.

## Cohort and known bias

- Public video metadata already present in the production collection is exported
  for 2026-01-01 through 2026-08-13.
- The candidate file contains video id, channel id, title, truncated description,
  category and publication time only. Engagement fields are rejected by the
  loader.
- Only channels whose stored default language starts with `en` are included.
- The monitored channel universe was assembled using information available in
  2026, so historical inclusion has survivorship and discovery-selection bias.
  The result is a development diagnostic, never a blind product claim.

## Frozen temporal split

- Train checkpoints: weekly from 2026-03-01 through 2026-05-25.
- The first 75% of train checkpoints fit the regularized logistic model.
- The last 25% of train checkpoints calibrate probabilities with Platt scaling.
- Development test checkpoints: weekly from 2026-06-01 through 2026-07-02.
- The latest test checkpoint must have the full 42-day outcome window before the
  script will run.
- A topic has a 42-day episode cooldown across the complete train/test timeline.

## Candidate universe

At a checkpoint, before applying any score, a topic requires:

- 2–60 active videos during the preceding 35 days;
- at least 2 independent channels;
- at least 1 video during the preceding 7 days;
- specificity at least 70 and thesis support at least 0.8;
- a visible format-neutral microtopic identity.

## Frozen adoption outcome

During the following 42 days a positive outcome requires:

- at least 4 future videos;
- future supply at least 1.25 times the preceding 28-day rate extrapolated to
  42 days, with an expected-supply floor of 2;
- at least 2 channels that had not published in the topic during the preceding
  180 days;
- at least 40% of future videos published by those new channels.

## Model, baselines and gate

The model uses only structural features available at the checkpoint: recent and
preceding supply, acceleration, creator counts and entropy, new-creator share,
topic age and specificity. It is compared on exactly the same test episodes with
legacy score, recent supply, acceleration and creator breadth rankings.

Reported metrics are positive support, base rate, top-quintile precision/recall
and lift, average precision, Brier score versus a constant-prevalence forecast,
expected calibration error and median lead time. The test also reports a
deterministic topic-level bootstrap interval for model lift.

Directional gate:

- at least 20 positive test episodes;
- top-quintile lift at least 1.5;
- average precision above base rate;
- Brier score below the constant-prevalence baseline;
- expected calibration error no more than 0.15;
- median lead time at least 7 days;
- model top-quintile precision no worse than every simple ranking.

Even if all gates pass, the result may only justify collecting a fresh untouched
future cohort. It cannot change production weights or decisions by itself.

