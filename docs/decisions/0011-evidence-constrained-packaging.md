# ADR 0011: Packaging is selected-opportunity only and evidence constrained

- Status: Accepted
- Date: 2026-07-28

## Context

An actionable opportunity still leaves a creator with a packaging problem, but
generating a full script or unsupported result claims would move outside the MVP
boundary and weaken evidence integrity.

## Decision

`signal-packaging-v1` is created only after a user selects an opportunity and a
content brief exists. It produces an audience promise, core tension, three hook
directions, ten distinct title strategies, three text-only thumbnail directions,
proof requirements, mismatch risks, and a recommended opening structure.

Every record stores the selected opportunity, content brief, evidence IDs,
version, and per-section regeneration counts. Individual sections can be
regenerated without changing the rest of the package. Copy events are logged for
product learning.

Templates use questions, test framing, and explicit proof requirements. They do
not assert unmeasured outcomes, invent numbers, guarantee performance, generate
thumbnail images, or generate a full script.

## Consequences

- Packaging stays traceable to the decision and source evidence.
- Title directions deliberately cover different strategies rather than surface
  variations of one sentence.
- Results or winners must be supplied by new production evidence.
- The feature remains removable through `FEATURE_SIGNAL_PACKAGING`.
