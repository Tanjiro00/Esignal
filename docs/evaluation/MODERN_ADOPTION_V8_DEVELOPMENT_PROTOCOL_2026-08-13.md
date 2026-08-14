# Modern YouTube adoption v8 development replay

Protocol frozen: 2026-08-13, before building or evaluating the v8 challenger on
the June development-test partition.

## Why a new challenger is necessary

The preregistered v7 preflight produced only 22 train and 14 test episodes. Its
June development-test base rate was 13/14 because identities such as
`ChatGPT creator activity` and `Claude Code creator activity` combined unrelated
claims into product-wide buckets. The probability model correctly refused to
fit on 13 fitting examples.

That is a candidate-universe failure, not evidence that the ranking method
works. The v7 protocol, code and diagnostic counts remain preserved.

## Frozen v8 identity rule

The challenger uses title text available at publication time only. An identity
must contain:

- a named product/model (including a material version) or a narrow AI domain;
- a concrete claim object, capability, use case or event;
- no presentation format (`tutorial`, `review`, `short`, `podcast`, etc.) in its
  stable key.

Examples of admissible neutral identities are `Claude Code — memory and context`,
`DeepSeek V4 — price and inference cost`, and
`AI video generation — consistent characters`. A product name with only generic
activity is rejected. Comparison identities require two named products and are
keyed independently of title order.

The taxonomy is deterministic. It does not use views, likes, comments, future
titles, an LLM, or corpus-wide frequency statistics. Training-title inspection
may add missing deterministic aliases before the implementation is frozen; no
June label or v8 June prediction may be inspected during that work.

## Temporal split, candidate policy and outcome

All remaining rules are unchanged from
`MODERN_ADOPTION_DEVELOPMENT_PROTOCOL_2026-08-13.md`:

- train checkpoints weekly from 2026-03-01 through 2026-05-25;
- first 75% of train checkpoints for fitting and last 25% for calibration;
- development-test checkpoints weekly from 2026-06-01 through 2026-07-02;
- 42-day topic cooldown and complete 42-day future outcome horizon;
- candidate history of 2–60 videos in 35 days, at least 2 channels, at least 1
  recent video, specificity at least 70 and thesis support at least 0.8;
- positive adoption requires at least 4 future videos, at least 1.25x expected
  supply (expected floor 2), at least 2 new channels and at least 40% future
  supply from new channels.

The directional gate is also unchanged: at least 20 positive test episodes,
top-quintile lift at least 1.5, average precision above base rate, Brier below
the constant forecast, ECE at most 0.15, median lead at least 7 days and no worse
precision than the simple rankings.

## Interpretation boundary

This is a selection-biased development cohort assembled from the current
monitoring universe. A pass can only authorize a fresh untouched prospective
cohort. It cannot change production weights, probabilities or `Act` decisions.
