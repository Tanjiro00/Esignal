# EarlySignal UX simplification implementation

Date: 2026-07-28  
Specification: `EARLYSIGNAL_UX_SIMPLIFICATION_CODEX_SPEC_RU.md`

The slices below were executed sequentially because the user explicitly asked
to complete the full specification in one delivery. Core scoring weights,
ingestion providers, evidence storage and provenance were not changed.

## Slice status

| Slice | Implementation | API/data | Verification | Feature flag and rollback |
| --- | --- | --- | --- | --- |
| 0 — Baseline | Route, terminology, state, journey and component audit; production desktop/mobile captures | None | `earlysignal-current-ux-baseline.md` and `docs/ux/baseline/*` | No behavior change |
| 1 — Navigation | Primary nav is Today, Opportunities, Briefs, Results, Settings; old routes redirect; admin nav and layout role-gated | Context adds `role`, `is_admin`, `features` | Desktop sidebar and mobile bottom nav e2e | `FEATURE_UX_SIMPLIFIED_NAVIGATION_V1`; previous web image restores old shell |
| 2 — Today | Default route; 1–3 ranked opportunities; stable skeleton; filtered-noise and no-decision state | Existing digest and signal feed | Act card, empty-state and route tests | `FEATURE_UX_TODAY_HOME_V1`; `/digest` API preserved |
| 3 — Decision card | Decision, concrete video, why now/channel, open angle, publish-by, production, evidence and risk; Act/Watch/Skip | Additive consolidated decision-card endpoint; production plan metadata | Unit, integration and e2e decision flow | `FEATURE_UX_DECISION_CARD_V1`; raw signal contracts unchanged |
| 4 — Opportunity Detail | Decision, Content gap, Evidence, Lifecycle and Why this channel tabs; technical disclosure closed; mobile sticky actions | Existing Signal Detail contract | Desktop tab and mobile sticky-action e2e | `FEATURE_UX_OPPORTUNITY_DETAIL_V2`; old signal URL redirects |
| 5 — Scores and terms | User routes say Opportunity/Results and use qualitative buckets; decimals/raw components limited to technical/admin | Raw scores preserved | Copy inspection, typecheck and browser QA | `FEATURE_UX_SIMPLE_SCORES_V1`; no score migration |
| 6 — Onboarding | Three steps: connect, five fit choices, select 3–5 monitored channels; explicit example card | Additive monitored-channel active PATCH; context works before owned channel exists | Three-step e2e and analytics events | `FEATURE_UX_ONBOARDING_V2`; old onboarding service remains |
| 7 — Brief v2 | One-page producer handoff with copy, share link, Markdown export and production started | Brief accepts `in_production`; production event stored | Unit clipboard fallback and e2e | `FEATURE_UX_BRIEF_V2`; brief JSON/evidence versions preserved |
| 8 — Results v2 | Automatic association confirmation, 24h/7d placeholders, channel-relative uplift and non-causal copy | Existing outcome/suggestion APIs | Linked result and empty-state e2e | `FEATURE_UX_RESULTS_V2`; `/outcomes` redirects |
| 9 — Notifications/Watch | Today is the in-app push surface; twice-weekly/weekly quiet digest; Watch requires meaningful condition; low-change watched topics suppressed from Today | Existing subscription/action persistence | Settings and decision tests | Uses Today/decision flags; no email is claimed before deliverability exists |
| 10 — Instrumentation | Required UX events, decision/onboarding funnels and elapsed-time metadata; admin beta dashboard | Additive event literals and analytics `ux` object | Integration contract plus `/admin/ux` | Additive and safe to ignore by older clients |

## Accessibility and responsive checks

- Semantic headings, tab roles, dialog labels and `aria-live` decision status;
- text + icon + color for Act, Watch and Skip;
- visible focus and reduced-motion behavior;
- shared controls have at least 44 px touch height;
- mobile bottom navigation and sticky Opportunity actions;
- evidence uses a vertical list rather than a primary table on mobile;
- loading skeleton preserves the Today decision-card footprint.

## Feature flags

```text
ux_today_home_v1
ux_decision_card_v1
ux_simple_scores_v1
ux_simplified_navigation_v1
ux_onboarding_v2
ux_opportunity_detail_v2
ux_brief_v2
ux_results_v2
```

They are exposed through `/api/v1/context` and configured with corresponding
`FEATURE_UX_*` environment variables. The changes are additive at the API and
database levels. The operational rollback is to disable the rollout flags and
redeploy the previous web image; no evidence or outcome data must be deleted.

## Analytics events

Implemented:

```text
today_opened
opportunity_card_viewed
opportunity_opened
why_recommended_opened
evidence_opened
technical_details_opened
act_clicked
watch_clicked
skip_clicked
decision_reason_selected
brief_created
brief_shared
production_started
result_opened
onboarding_started
onboarding_step_completed
onboarding_completed
```

Median time from Today to opportunity, decision/brief, and onboarding elapsed
time are derived only from stored event metadata. Missing timing samples remain
`null`; they are never invented.

## QA artifacts

- Before: `docs/ux/baseline/*`
- After: `docs/ux/qa/ux-v2-*.png`
- Required automated flow: `apps/web/e2e/demo-workflow.spec.ts`

The browser suite covers Today, empty Today, decision changes, Opportunity
tabs, closed technical details, mobile sticky actions, onboarding, brief copy
and share, production started, linked Results and empty Results.

## Production validation

- Deployed to `http://45.129.124.109` after a verified PostgreSQL backup.
- Production runs with `demo_mode=false`; the automatic feed resolves to
  approved live evidence and does not mix approved demo fixtures into Today.
- The final live review retained the specific AI-video workflow signal and
  rejected a broader AI-agent false merge.
- Creator-facing content gaps defensively replace channel mission copy with a
  supported audience label and expose qualitative channel-fit explanations
  instead of raw or contradictory scores.
- Final verification: 101 backend tests, 10 frontend tests and 7 browser E2E
  flows passed, followed by a production browser walkthrough.
