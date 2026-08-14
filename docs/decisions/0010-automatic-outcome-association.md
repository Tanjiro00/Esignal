# ADR 0010: Automatic outcome association is suggestive, auditable, and non-causal

- Status: Accepted
- Date: 2026-07-28

## Context

Manual outcome entry creates enough friction that signal-to-publication learning
is usually lost. A title match alone is also too weak to silently claim that a
published video came from an EarlySignal brief.

## Decision

`outcome-association-v1` compares every newly observed owned-channel upload with
active briefs using title, description/topic evidence, and time from brief to
publication. It creates one idempotent suggestion per workspace and canonical
video. A user must confirm it, reject it, or select another brief.

`outcome-metrics-v1` compares the confirmed upload with prior uploads that match
content type, duration range, topic-family proximity, upload period, and
sponsorship class. It records 24-hour, 72-hour, 7-day, and 30-day views when
snapshots exist, plus verified owned analytics when available. The user-facing
term is “associated uplift”; the system never presents the association as
causal proof.

Confirmed links can be corrected or unlinked without deleting their audit
history. Detection and metric refresh run asynchronously in the worker and
remain behind `FEATURE_OUTCOME_SUGGESTIONS`.

## Consequences

- Outcome confirmation takes one click for the proposed brief and two clicks
  when choosing an alternative.
- Workspaces without OAuth still receive view-based outcome updates from
  monitored owned uploads.
- Missing snapshots produce explicit pending metrics rather than estimates.
- The association, baseline cohort, model versions, and user decision remain
  inspectable.
