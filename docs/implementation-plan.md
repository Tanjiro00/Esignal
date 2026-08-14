# Implementation plan

1. Establish repository contracts, ADRs, local infrastructure, and demo-only
   configuration.
2. Create SQLAlchemy models and an Alembic baseline for the Slice 1 action loop.
3. Seed deterministic demo evidence: 5 topics, 50 channels, 300 videos,
   snapshots, comments, demand clusters, selected transcripts, signal actions,
   one brief, and one published outcome.
4. Implement `/api/v1` signal, brief, outcome, and provider-admin contracts.
5. Build a responsive evidence-dense feed, complete signal detail page, and mock
   provider operations view.
6. Verify the save → brief → outcome workflow with unit, integration, and
   Playwright tests.

## Repository inventory at start

The repository was empty except for `.git`. The MVP specification existed in
`/Users/daniil/Downloads` and was copied to the repository root as the source of
truth. No application code, package manifest, infrastructure, tests, or local
instructions existed.

## Visual specification

The implementation follows the accepted concepts in `docs/design-concepts/`:

- `signals-feed.png`
- `signal-detail.png`
- `providers-admin.png`

Design tokens: true cool-white canvas, charcoal text, slate metadata, acid-lime
growth accent, coral risk accent, hairline borders, minimal shadow, 8px control
radii, open lists/tables, disciplined UI typography, and a selective editorial
serif for research headings.

## Slice 2–3 status

Completed:

1. Added typed request/evidence contracts and capability routing boundaries.
2. Added content-addressed gzip raw payload storage, deterministic request
   fingerprints, provider fetch rows, health/budget accounting, field
   provenance, entity links, and zero-cost replay.
3. Added the isolated `youtube_web` public search and channel-RSS discovery
   adapter.
4. Added `youtube_official` video and channel metadata adapters with batched
   calls.
5. Added discovery query/run/occurrence tables, deterministic scheduling,
   monitored channels, global YouTube ID deduplication, and normalized upserts.
6. Added admin discovery controls and live/demo provider labeling.
7. Added sanitized provider fixtures, contract tests, and a real smoke run from
   query to five normalized video records.

Deferred by the Slice 2–3 boundary: statistics scheduling, velocity/outlier
features, topic clustering, comments, transcripts, and real user-facing
signals.

## Slice 4–5 status

Completed:

1. Added scheduled immutable video snapshots, channel baselines, view velocity,
   acceleration, and channel-relative outlier features.
2. Added versioned deterministic local embeddings and normalized AI/technology
   entities.
3. Added hybrid entity, lexical, and cosine topic assignment with stable topic
   identities and a two-video/two-channel confirmation floor.
4. Added immutable topic snapshots, transparent Early Signal component scoring,
   lifecycle stages, confidence, saturation, and source-fragility penalties.
5. Added idempotent pipeline runs, stale-topic archival, lag/coverage metrics,
   worker integration, and an Admin → Providers rebuild surface.
6. Added automatic live/demo routing in Signals, real evidence provenance, and
   explicit limitations for unavailable comment demand and provisional channel
   fit.

At the Slice 5 boundary, live comment collection and audience-demand clustering,
transcripts, provider benchmarking, and personalized channel fit remained
deferred.

## Slice 6 status

Completed:

1. Added official YouTube comment sampling plus an isolated scraping-first web
   fallback behind the existing typed comment-provider contract.
2. Added idempotent relevance/newest fetch runs, immutable privacy-minimized raw
   payloads, normalized comment deduplication, field provenance, and operational
   metrics.
3. Added versioned deterministic comment embeddings, the full demand taxonomy,
   spam/demand probabilities, and sentiment.
4. Added intent clustering with hard two-commenter/two-video/two-channel
   evidence floors, stable cluster IDs, representative verbatim snippets, and
   transparent demand scoring.
5. Integrated confirmed demand into topic snapshots, Early Signal Score,
   explanations, evidence-linked content angles, live feed/detail UI, and Admin
   controls.

## Slice 7 status

Completed:

1. Added a typed public-caption provider using native captions first and
   YouTube auto-captions second, with privacy-safe failure recording and
   zero-cost provider accounting.
2. Added high-value candidate selection, stable fetch idempotency, graceful
   unavailable/failed states, transcript pipeline runs, and coverage/lag
   metrics.
3. Added normalized full-text storage, content hashes, transcript provenance,
   quality/type/language metadata, timed segment storage, and generated-cost
   fields.
4. Added deterministic extractive summaries, entities, key claims, use cases,
   comparisons, questions, format/angle classification, segment embeddings,
   and bounded evidence selection.
5. Integrated transcript summaries and entities at medium weight into versioned
   topic embeddings, evidence-linked content angles, signal explanations, the
   signal detail UI, and Admin controls.
6. Redacted transcript text from provider payload APIs and exposed only short
   timestamped excerpts in product contracts.

Deferred after Slice 7: broader provider benchmarking and production routing
(Slice 8), and personalized channel fit (Slice 9).
