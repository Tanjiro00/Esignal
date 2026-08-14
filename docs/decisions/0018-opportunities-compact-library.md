# ADR 0018: Compact grouped Opportunities library

Status: accepted

## Context

The post-audit baseline rendered the complete decision card on both Today and
Opportunities. This made the library slow to scan, repeated the same controls
and evidence preview, and obscured the distinction between deciding what to do
today and browsing the full opportunity history.

The existing signal and brief APIs already expose the fields needed to organize
the library without changing scoring or evidence contracts.

## Decision

Opportunities becomes a compact status-grouped library.

The fixed groups are:

- Needs decision;
- Watching;
- In production;
- Skipped;
- Expired.

Each row shows the evidence-grounded recommended video, stable trend title,
source count, suggested decision, lifecycle stage, publish window, channel-fit
bucket, and workflow status. Opening a row navigates to Opportunity Detail,
where the complete decision card and evidence remain available.

Grouping is deterministic:

1. a non-archived brief or an `act` action is In production;
2. explicit Watch and Skip actions use their matching groups;
3. closed opportunity windows and Saturated or Declining topics are Expired;
4. the remaining signals Need decision.

The latest non-archived brief per signal supplies the workflow status. Signal
and brief requests run in parallel after workspace context is resolved.

Desktop uses a comparison table-like row. Mobile uses the same link and data
contract in a compact three-column metadata layout with horizontally scrollable
group navigation. Full decision controls are not rendered in the library.

## Consequences

- Today remains the focused decision surface.
- Opportunities supports fast comparison and status navigation.
- No API, database, score, evidence, review, or release-policy behavior changes.
- A brief creation or decision invalidates both the library and detail query so
  visible workflow state refreshes.

## Verification

Grouping helpers have deterministic unit coverage. End-to-end coverage verifies
group navigation, compact rows, detail/evidence navigation, Watch/Skip
replacement, empty states, mobile density, and lack of page overflow.

Visual captures are stored under `docs/post-audit-slice-2/screenshots/`.

## Rollback

Restore the previous Opportunities page mapping to
`OpportunityDecisionCard`. The shared card and all API contracts remain
available and unchanged.
