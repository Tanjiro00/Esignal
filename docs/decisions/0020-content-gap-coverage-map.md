# ADR 0020: Evidence-grounded content gap coverage map

Status: accepted

## Context

Opportunity Detail previously led with an unanswered question and rendered
three generic “Open evidence gap” rows. The underlying signal already stored a
more useful distinction between occupied coverage, an open content cell,
audience demand, proof requirements, production effort, evidence strength, and
ranked content angles, but the creator UI did not expose that structure.

This made it difficult to understand what the market had already covered, what
was genuinely missing, why the gap was open, and how the alternatives differed.

## Decision

Content gap presentation is built only from stored signal data:

- the strongest released demand cluster supplies the concrete primary gap
  label and audience question;
- the rank-one content gap supplies occupied coverage, the open claim,
  audience, proof requirement, production complexity, evidence strength, and
  source references;
- the content angle with the same stable `gap_key` supplies the promise,
  differentiation, production effort, and neutral open-angle title;
- `video:*` evidence references resolve to the signal’s stored evidence videos
  and canonical YouTube URLs.

The primary view exposes:

- Why it is open;
- Audience;
- Promise;
- What current videos cover;
- What current videos miss;
- Required proof;
- Production effort;
- Evidence strength;
- direct source links.

A four-stage coverage map makes the progression explicit:

1. Well covered;
2. Under-covered;
3. Unanswered audience demand;
4. Recommended open angle.

At most two alternatives are shown. Selection is deterministic by stored rank.
Alternatives with the same normalized claim, proof type, context, and audience
as a higher-ranked gap are removed, so wording-only duplicates are not
released.

The content gap does not prescribe a video format. Format may remain in stored
technical data, while the creator-facing recommendation is organized around
the audience problem, open claim, and required proof.

The route supports `?section=content-gap` so the redesigned state can be linked
and audited directly.

## Consequences

- Creators can distinguish occupied coverage from an actual open angle without
  opening technical details.
- Every visible gap statement resolves to stored deterministic, demand, angle,
  or evidence data.
- Source discovery is available in the primary view.
- No database, provider, score, release-policy, or LLM behavior changes.

## Verification

Unit coverage verifies stable rank ordering, `gap_key` joins, duplicate
alternative removal, and evidence-reference resolution. End-to-end coverage
verifies every primary field, all four coverage states, source links, exactly
two distinct demo alternatives, the stable deep link, mobile typography, and
lack of horizontal overflow.

Desktop and mobile captures are stored under
`docs/post-audit-slice-4/screenshots/`.

## Rollback

Restore the previous inline `ContentGap` implementation in
`OpportunityDetail`. Signal, content-angle, and content-gap API contracts remain
unchanged.
