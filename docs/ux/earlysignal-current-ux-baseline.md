# EarlySignal current UX baseline

Date: 2026-07-28  
Baseline environment: production demo at `http://45.129.124.109`  
Change boundary: observation only. This document records the interface before
the UX simplification rollout.

## Route inventory

| Route | Current purpose | Main dependency | Future placement |
| --- | --- | --- | --- |
| `/` | Redirects to Digest | none | Redirect to Today |
| `/digest` | Three ranked decision cards | digest, subscription, signal actions | Today |
| `/signals` | Dense split-view signal explorer | signal feed | Opportunities |
| `/signals/{id}` | Signal detail and evidence | signal detail, earlyness, actions | Opportunity detail |
| `/pulse` | Product analytics, freshness and recent activity | analytics summary, digest | Results and admin UX analytics |
| `/watchlists` | Owned/reference/competitor channels | monitored channels | Settings → Monitored channels |
| `/briefs` | Brief list and packaging kit | briefs, outcomes, packaging | Briefs v2 |
| `/outcomes` | Outcome suggestions and performance | outcomes, suggestions | Results |
| `/settings` | Channel profile, production and OAuth | channel profile, OAuth | Settings v2 |
| `/onboarding` | Multi-section workspace setup | onboarding, profile, monitored channels | Three-step onboarding |
| `/admin/review` | Signal review queue | review API | Admin-only |
| `/admin/evaluation` | Evaluation labels and reports | evaluation API | Admin-only |
| `/admin/operations` | Pipeline readiness | operations API | Admin-only |
| `/admin/queries` | Query suggestions | query-expansion API | Admin-only |
| `/admin/providers` | Providers and monitored sources | provider API | Admin-only |

Current primary navigation is Digest, Signals, Pulse, Watchlists, Briefs,
Outcomes and Settings. Admin navigation is always rendered, regardless of
workspace role.

## Current journey

1. Onboarding asks the user to configure a workspace, owned channel, inferred
   profile, reference channels, topic universe and digest.
2. Digest presents ranked signal decisions. Signals presents the same underlying
   objects as a denser analyst workspace.
3. A signal detail combines the recommendation with evidence, demand,
   lifecycle, content-gap and technical score material.
4. Act creates a brief immediately; production effort and target date are not
   confirmed first.
5. Briefs expose packaging inside a nested disclosure and allow linking a
   published video.
6. Outcomes shows suggested associations and stored performance relative to a
   baseline.
7. Pulse exposes product funnel and operational freshness to the user.

The flow is functionally connected, but the same object is described as
Signal, opportunity, angle and digest item across different screens.

## Visible terminology and numbers

Technical or internally-oriented terms currently visible include:

- Signal, Early Signal Score, channel fit, confidence, lifecycle stage;
- Seed, Emerging, Breakout, Mass Market, Saturated and Declining;
- momentum, outlier ratio, view velocity, saturation score and diffusion;
- evidence version, fit version, profile version and data mode;
- baseline coverage, transcript coverage, specificity score and calibrated;
- demand cluster, independent spread, provenance and snapshot freshness;
- source mode, provider health, dead letter and ingestion run;
- opportunity ID, evidence ID and raw YouTube IDs.

Decimal score-like values are visible in Signals, Signal Detail, Pulse and
Outcomes. The current Digest already uses qualitative decision and evidence
buckets, but supporting pages revert to raw analyst terminology.

## Current interface states

- Loading: shared skeleton page, but its four tall rows do not match every
  destination and can shift at hydration.
- Empty Digest: explains that reviewed evidence has not passed the floor.
- Empty evidence and transcript states: present in Signal Detail.
- Empty Briefs and Outcomes: no dedicated guidance or next action.
- Error: shared retry state, phrased as an evidence-loading failure even on
  Settings, Briefs and Outcomes.
- Success: mutations mostly rely on the changed row; settings has an explicit
  saved message. Decision changes do not have a screen-reader status.
- Demo: visually identified in the shell and data mode labels.

## Pulse and Watchlists migration

Move to Today:

- last meaningful update;
- filtered-noise count;
- strong Act notification summary;
- watched topic meaningful-change notice.

Move to Results:

- brief-to-published funnel;
- channel-relative performance;
- outcome association state.

Move to admin-only analytics:

- provider freshness and health;
- discovery/snapshot timestamps;
- dead letters;
- internal event stream and raw funnel diagnostics.

Move Watchlists to Settings as “Monitored channels”. Preserve owned,
reference and competitor relationships and the existing ingestion APIs.

## Component architecture

`AppShell` owns responsive navigation and workspace context. Page components
use TanStack Query directly and compose a small shared UI layer (`Button`,
`PageLoading`, `ErrorState`, `PageHeader`). Signal UI is split between
`SignalFeed`, `SignalDetailView`, `DecisionFeedback`, `EarlynessTimeline` and
`Sparkline`. Brief, Outcomes, Settings and Onboarding are page-local
implementations with limited shared flow components.

The frontend depends on stable `/api/v1` contracts through `apps/web/lib/api.ts`
and `apps/web/lib/types.ts`. Digest and Signal Detail already receive a
server-computed `decision_card`; raw recommendation synthesis should remain on
the server.

## Analytics coverage

Currently stored:

- signal impression/open/evidence interaction;
- act/watch/skip/save/dismiss;
- brief created;
- outcome linked/confirmed/rejected/unlinked/successful;
- packaging copy;
- digest generated;
- onboarding completed.

Missing for usability analysis:

- Today opened and opportunity card viewed;
- why-recommended, evidence and technical-detail disclosure;
- button click separated from completed decision;
- decision reason selected;
- brief shared and production started;
- result opened;
- onboarding started and per-step completion;
- time-to-first-understanding, time-to-decision and time-to-brief.

## Baseline captures

Desktop:

- `baseline/digest-desktop.png`
- `baseline/signals-desktop.png`
- `baseline/signal-detail-desktop.png`
- `baseline/pulse-desktop.png`
- `baseline/watchlists-desktop.png`
- `baseline/briefs-desktop.png`
- `baseline/outcomes-desktop.png`
- `baseline/settings-desktop.png`
- `baseline/onboarding-desktop.png`

Mobile:

- matching `*-mobile.png` captures for Digest, Signals, Signal Detail, Pulse,
  Briefs, Outcomes and Settings.

## Primary UX blockers

1. Seven primary destinations expose system architecture instead of the five
   questions a creator needs answered.
2. Digest is decision-first, but Signals and Pulse pull the user back into a BI
   mental model.
3. The idea, why now, channel fit and publish-by date do not stay in a stable
   visual position across screens.
4. Act skips production-time confirmation.
5. Briefs are list rows with a nested technical packaging disclosure rather
   than one producer handoff.
6. Empty states in Briefs and Outcomes do not tell the user how to create the
   first item.
7. Admin and operational data are visible to every workspace member.

## Slice 1 blockers

No backend blocker. Existing routes and APIs can be preserved as compatibility
redirects. Role and feature-flag values must be exposed in workspace context so
the new navigation can be rolled back and admin links can be gated.
