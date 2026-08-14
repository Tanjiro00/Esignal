# ADR 0017: Recommendation-first Today hierarchy

Status: accepted

## Context

The post-audit baseline showed that Today made the detected trend more prominent
than the actionable video recommendation. Users had to scan the trend thesis,
format-neutral angle, source list, and technical fit disclosure before they
could understand what to make.

On mobile, decision controls were not attached to the primary Today
opportunity. The existing sticky control used icon-only secondary actions,
duplicated the regular controls for assistive technology, and did not account
for device safe areas.

## Decision

The Today surface uses a dedicated presentation variant of the existing typed
decision card:

- the evidence-grounded recommended video is the card heading;
- the lifecycle stage and stable trend title are visible as secondary context;
- `Why now` and `Why this channel` remain visible at the first level;
- source links move into a collapsed, count-labelled evidence disclosure;
- publish deadline, production estimate, evidence strength, and main risk stay
  visible beside the primary action;
- digest refresh becomes a compact secondary action next to the last-updated
  time;
- only the highest-priority Today card owns the mobile sticky actions;
- every sticky action has a visible label, the primary action is `Create brief`,
  and the bar is positioned above navigation with safe-area support;
- the non-sticky action controls are removed from the mobile accessibility tree
  when the sticky controls are present;
- Watch and Skip display a saved confirmation after the mutation completes.

The Opportunities list and opportunity detail keep their existing hierarchy.
No API contract, evidence, ranking, score, or release-gate behavior changes.

## Verification

The hierarchy is covered by component and end-to-end tests. Visual QA compares
the original Today baseline with 1440 × 900 desktop and 390 × 844 mobile
captures stored under `docs/post-audit-slice-1/screenshots/`.

## Rollback

Revert the Today card `surface="today"` usage and the compact header changes.
The shared default decision-card variant remains available and unchanged.
