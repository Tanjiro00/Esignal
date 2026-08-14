# ADR 0009: Channel Profile v2 and creator-specific opportunity decay

- Status: Accepted implementation
- Date: 2026-07-28
- Scope: Product improvement Slice 7
- Feature flag: `FEATURE_CHANNEL_PROFILE_FEASIBILITY_V2`
- Profile version: `channel-profile-v2`
- Decay version: `creator-specific-opportunity-decay-v1`

## Channel Profile v2

The inferred profile now strips URLs, domains, social handles, and sponsor
boilerplate before extracting topics. Recent uploads receive higher weight than
old history. Current, adjacent, and legacy topics are stored separately.
Shorts, long-form, and live uploads have distinct format treatment, and
historically successful formats require stored relative-performance evidence.

The profile includes:

- core, adjacent, excluded, and legacy topics;
- preferred and successful formats;
- typical duration and upload cadence;
- audience sophistication and creator authority;
- explicit strategic goals and brand-risk tolerance;
- team, research, filming, guest, editing, and product-access constraints;
- experiment level and evergreen/trend balance;
- weekday rules and blocked content-calendar dates.

The inference payload remains stored for inspection. User-confirmed fields are
stored in `explicit_overrides_json`, set `profile_source=user`, and take
precedence in channel-fit scoring.

## Production feasibility

Each opportunity receives a deterministic estimate and absolute publish-by
date in the workspace timezone. The decay model considers:

- lifecycle stage;
- adoption rate;
- observed large-channel entry;
- channel production range;
- team and research capacity;
- filming, guests, editing, and product access;
- weekday-only publishing;
- blocked content-calendar dates.

The output includes estimated minimum/maximum days, recommended publish-by,
High/Medium/Infeasible feasibility, reason codes, timezone, decay days, and
model version.

An opportunity with minimum production time beyond the publish-by date is
never eligible for `Act`. The unified decision card returns `Skip` with
`production_window_infeasible` and exposes the concrete constraint.

## Compatibility and rollout

All new profile fields are additive. Existing profile fields and channel-fit
components remain available. Fit results now preserve reason codes.

Rollout:

1. apply the profile migration;
2. load or re-infer profiles;
3. have each user confirm explicit settings;
4. rebuild live signals with the flag enabled;
5. verify absolute dates in the workspace timezone and inspect infeasible
   decisions.

Rollback disables the feature flag. Legacy production ranges remain stored and
the decision card falls back to the previous window comparison.
