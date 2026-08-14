# ADR 0014: The creator surface is decision-first and evidence-second

- Status: Accepted
- Date: 2026-07-28

## Context

The original private-beta UI exposed the internal intelligence architecture as
Digest, Signals, Pulse, Watchlists, Briefs and Outcomes. It preserved evidence
well, but forced creators to interpret scores, lifecycle terms and operational
metrics before answering the product’s core question: should this channel make
this video now?

## Decision

The primary information architecture is Today, Opportunities, Briefs, Results
and Settings.

Today shows no more than three server-computed decision cards, ordered Act,
Watch and Skip. Every card presents the specific video idea, why now, channel
fit, open angle, publish-by date, production effort, evidence bucket and main
risk. Raw deterministic scores remain stored and are available only through a
closed Technical details disclosure or admin tools.

Opportunity Detail uses Decision, Content gap, Evidence, Lifecycle and Why this
channel tabs. Act confirms production time and target publish date before
creating a brief. Watch stores the meaningful condition that should cause the
topic to reappear. Skip stores an optional quality reason.

Briefs are producer handoffs, not copies of Signal Detail. Results compare
associated videos with the channel’s own baseline and never make a causal
claim. Watchlists move to Settings as Monitored channels. Pulse operations move
to admin analytics; outcome information moves to Results. Admin navigation and
routes are gated by workspace owner/admin role in the web application.

Existing `/api/v1` contracts and evidence/provenance storage remain intact. The
additive decision-card endpoint keeps recommendation synthesis on the server.
Compatibility URLs redirect to the new routes.

## Consequences

- A creator can understand and act without learning EarlySignal score
  methodology.
- Evidence remains auditable without dominating the first viewport.
- The simple and analyst experiences share the same stored facts.
- UX timing and decision funnels can be evaluated in private beta.
- The UI role gate is not a replacement for future server-side multi-tenant
  authentication and authorization.
- Rollback is controlled by the eight `FEATURE_UX_*` rollout flags plus
  deployment of the previous web image; no database rollback is required
  because API and schema changes are additive.
