# ADR 0005: Comment-to-topic relevance gate

- Status: Accepted implementation
- Date: 2026-07-28
- Scope: Product improvement Slice 3
- Feature flag: `FEATURE_COMMENT_TOPIC_RELEVANCE`
- Relevance version: `comment-topic-relevance-v1`
- Demand clustering version: `demand-intent-clustering-v3-relevance`

## Context

Repeated comment intent is useful only when the comments actually support the
specific microtopic. A generic question, praise, spam, or a matching phrase
about another product must not become audience-demand evidence merely because it
appears on videos assigned to the same topic.

The previous demand gate checked repeated intent across videos, channels, and
commenters. It did not persist an auditable comment-to-topic decision or require
an evidence chain from the comment through its source video to the topic's
entities and claims.

## Decision

Every live comment is classified against one topic before it can contribute to
a user-visible demand cluster. The deterministic classifier records:

- comment-to-topic semantic similarity;
- comment-to-source-video semantic similarity;
- topic entity overlap;
- supported claim concepts;
- intent actionability;
- duplicate or echo probability;
- spam probability;
- accepted/rejected decision and reason codes;
- input fingerprint and model version.

The current decision is stored in `comment_topic_relevance`.
`comment_topic_relevance_events` is an append-only audit trail for initial
classification, replay changes, and manual overrides. Raw comments and provider
provenance remain unchanged.

The MVP uses versioned local lexical and hashing features. An LLM may later
summarize stored evidence or shortlist uncertain rows, but it cannot set the
deterministic trend score.

## User-visible demand gate

When the feature flag is enabled, a cluster becomes `user_visible` only when it
contains:

- at least 3 accepted relevant comments;
- at least 2 source videos;
- at least 2 independent channels;
- at least 3 commenter hashes;
- median relevance of at least `0.70`;
- at least 1 high-actionability comment;
- entity or claim support when the topic has a product anchor.

Clusters that fail the gate remain `internal_candidate`. They are retained for
evaluation and diagnostics but are excluded from user APIs, scoring evidence,
opportunities, quotes, and the signal UI.

Evidence strength is exposed as `Strong`, `Moderate`, or `Weak`. User-facing
surfaces show this label and relevant-comment counts, not raw classifier
decimals. Quotes remain verbatim stored comments and link to their source video.

## Replay and overrides

`POST /api/v1/admin/demand/reclassify` re-evaluates stored live comments,
rebuilds demand clusters, and reruns topic intelligence. Repeating an unchanged
replay is idempotent and does not append duplicate audit events.
PostgreSQL transaction-level advisory locks serialize relevance classification
and demand clustering, so a scheduler run and a manual replay cannot write the
same current-state rows concurrently.

An admin reviewer can accept, reject, or return an individual classification to
the model decision. The effective decision is persisted separately from the
model result, the actor and note are audited, and a manual override survives
later model replay.

Operational metrics include evaluated, accepted, and rejected comments,
rejection rate, median relevance, internal-candidate count, and model version.

## Compatibility and rollout

The migration is additive. Existing demand rows default to `legacy_visible`,
and the feature-off path keeps the previous clustering behavior and API
responses. Admin relevance endpoints return `404` while the flag is disabled.

Rollout order is:

1. create and verify a database backup;
2. deploy code with the flag off;
3. apply the additive migration;
4. enable the flag for API and worker;
5. replay stored comments;
6. inspect rejection rate, visible/internal clusters, review evidence, and
   source links.

Rollback can disable the flag without deleting new records. The audit tables
remain available for later calibration.

## Consequences and limitations

- Generic praise, vague requests, spam, unsupported product mentions, and exact
  author echoes no longer count as market demand.
- The persisted comment/video/topic chain creates labeled data for future
  calibration and outcome attribution.
- Hashing semantics are intentionally cheap and reproducible, but weaker than a
  calibrated semantic model on paraphrases, neighboring products, and ambiguous
  references.
- Topic titles, descriptions, and current product anchors bound the available
  claim context. Production labels and review overrides are required before
  changing thresholds or replacing the classifier.
