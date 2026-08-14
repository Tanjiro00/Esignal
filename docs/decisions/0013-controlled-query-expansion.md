# ADR 0013: Query expansion is evidence anchored and human activated

- Status: Accepted
- Date: 2026-07-29

## Context

Static discovery queries miss new product names and problem language. Automatic
activation, however, can rapidly increase provider cost and fill the evidence
pool with broad or irrelevant videos.

## Decision

`query-expansion-v1` proposes candidates from product entities, co-occurring
title phrases, comment demand, related terms, release names, monitored
watchlists, transcript entities, and topic identity changes. Every suggestion
stores its source entity, topic, evidence IDs, rationale, product/problem
anchors, broadness score, and model version.

Candidates without both a product and a problem anchor, exact duplicates, and
broad phrases are not admitted to the review queue. A run can create at most ten
suggestions, and the pending queue is capped at fifty.

Approval creates an inactive discovery query. Activation is a separate admin
action. Completed discovery runs calculate retained-result precision. After at
least twenty results, precision below 15% marks a query `low_value` and pauses
it automatically; no query is automatically reactivated.

## Consequences

- Admins can see why each query exists and which evidence produced it.
- Query cost growth has explicit per-run and queue bounds.
- Precision is comparable across manual and expanded queries.
- New sources can be added behind the typed candidate interface without
  changing ingestion provider contracts.
