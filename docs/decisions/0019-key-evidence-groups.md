# ADR 0019: Key evidence groups

Status: accepted

## Context

Opportunity Detail previously rendered every stored evidence video as one long
list. The list preserved provenance, but it made the recommendation difficult
to audit: primary movement, independent amplification, and background
corroboration looked equally important. Twelve nearly identical rows also hid
the source links and channel-relative signals users need first.

The existing signal contract already exposes provider-backed thumbnails,
channel metadata, publication age, outlier ratio, evidence role, transcript
status, and transcript-derived narrative angles. The redesign therefore does
not require a scoring or API-contract change.

## Decision

Evidence is grouped by its stored role:

- Drivers;
- Amplifiers;
- Supporting evidence.

The default view deterministically selects at most five key sources using role
quotas of two Drivers, two Amplifiers, and one Supporting source. Within each
role, stored transcript availability is preferred first, followed by
channel-relative outlier, view velocity, and recency. If a role cannot fill its
quota, the remaining slots use the same ordering across the unselected
evidence.

Unknown provider roles degrade to Supporting evidence. The selection never
changes deterministic trend scores, evidence roles, review state, or release
policy.

Every source row includes:

- the stored YouTube thumbnail URL and canonical source link;
- channel and subscriber context;
- publication age;
- channel-relative outlier;
- stored evidence role;
- transcript availability;
- transcript-derived angle contribution when one is stored;
- views as a secondary metric.

When no transcript-derived angle exists, the UI says so explicitly rather than
generating one. Failed or unavailable thumbnails keep a neutral video marker;
they are not replaced with invented imagery.

`Show all` expands the same grouped view to every stored source, and `Show key
evidence` restores the deterministic subset.

## Consequences

- The first evidence screen is scannable while complete provenance remains one
  action away.
- Source importance and corroboration are visually distinct.
- Evidence claims remain traceable to stored provider or demo data.
- No backend, database, model, scoring, or provider behavior changes.

## Verification

Unit coverage verifies the five-source cap, role diversity, transcript
preference, and unknown-role fallback. End-to-end coverage verifies all three
groups, the compact source fields, Show all/Show key evidence, mobile density,
and lack of horizontal overflow.

Desktop and mobile captures are stored under
`docs/post-audit-slice-3/screenshots/`.

## Rollback

Restore the previous evidence-video mapping in `OpportunityDetail`. The signal
contract and complete evidence collection remain unchanged.
