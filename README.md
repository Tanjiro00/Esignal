# EarlySignal

EarlySignal finds emerging English-language AI/technology topics on YouTube,
shows the evidence behind their momentum, and turns unmet audience demand into a
channel-specific content opportunity.

This repository implements the complete **Slices 1–10 private-beta MVP**:
provider-independent discovery, historical video intelligence, transparent
topic and signal scoring, audience-demand and transcript evidence,
channel-specific fit, brief-to-outcome attribution, onboarding, digest,
product analytics, and operational readiness.

The decision-quality improvement program has completed feature-flagged Slices
1–3.
See
[`docs/decisions/earlysignal-improvement-baseline.md`](docs/decisions/earlysignal-improvement-baseline.md)
for point-in-time production/demo fixtures, model versions, rollout flags,
and backup/restore evidence. The append-only lifecycle model, backfill, API,
and earlyness UI are documented in
[`docs/decisions/0003-earlyness-lifecycle-history.md`](docs/decisions/0003-earlyness-lifecycle-history.md).
The workspace-scoped human review gate, reason taxonomy, audit trail, and admin
workflow are documented in
[`docs/decisions/0004-human-signal-review-queue.md`](docs/decisions/0004-human-signal-review-queue.md).
The auditable comment-to-topic relevance gate, replay, and manual overrides are
documented in
[`docs/decisions/0005-comment-topic-relevance-gate.md`](docs/decisions/0005-comment-topic-relevance-gate.md).

## Quick start

Requirements: Python 3.12+, uv, Node 22+, npm, and Playwright Chromium.

```bash
make setup
make demo
```

Open [http://localhost:3000](http://localhost:3000). The FastAPI docs are at
[http://localhost:8000/docs](http://localhost:8000/docs).

The demo database is SQLite by default. To run the target local topology:

```bash
docker compose up --build
docker compose exec api uv run alembic upgrade head
docker compose exec api uv run python -m apps.api.seed
```

## Real ingestion

Copy `.env.example` to `.env` and configure `YOUTUBE_API_KEY`. Discovery does
not consume the official search API: it uses the isolated `youtube_web` parser
for public YouTube results and channel RSS feeds. The official API supplies
canonical video and channel metadata.

```bash
make service
```

`make service` starts the API, web app, and due-query scheduler. Useful
one-shot commands:

```bash
make seed-queries
make ingest-real
make refresh-video-intelligence
make run-snapshots
make build-signals
make refresh-demand
make refresh-transcripts
make generate-digest
make backup
make verify-backup
uv run python -m apps.worker run-query "AI coding agents" --force --limit 20
uv run python -m apps.worker monitor-channel UC_CHANNEL_ID --limit 15
```

The Signals feed automatically prefers live evidence when confirmed topics
exist and keeps the deterministic demo available as an explicit mode. Live
topics require at least two videos from two independent channels. The pipeline
uses versioned local title/entity embeddings, hybrid clustering, immutable topic
snapshots, and the transparent Early Signal score from the product
specification.

Promising live videos receive separate top and newest comment samples. The
official comments API is preferred when configured and an isolated public-web
adapter is the scraping fallback. Stored comments are deduplicated, classified
into the product taxonomy, and evaluated against the exact topic and source
video. With `FEATURE_COMMENT_TOPIC_RELEVANCE=true`, a user-visible demand
cluster requires at least three relevant comments from three commenters across
two videos and two independent channels, median relevance of at least 0.70, and
actionable entity or claim support. Weak clusters remain internal.
Representative UI quotes are always verbatim stored comments linked to their
source videos.

Selected high-value topic videos are enriched with public native or
auto-generated YouTube captions. The pipeline stores normalized text and timed
segments for evidence processing, but product APIs expose only bounded
extractive summaries and short timestamped excerpts. Missing captions never
block topic or signal generation, and external audio transcription remains
disabled.

The ingestion control surface is
[http://localhost:3000/admin/providers](http://localhost:3000/admin/providers).
It shows snapshot coverage, queue lag, velocity, acceleration, channel-relative
outliers, topic assignment, signal counts, transcript coverage, and freshness
alongside provider operations.
The human publication gate is at
[http://localhost:3000/admin/review](http://localhost:3000/admin/review).
With `FEATURE_SIGNAL_REVIEW_QUEUE=true`, live candidates enter `needs_review`
and are excluded from the feed, evidence page, digest, actions, briefs, and
outcomes until a reviewer approves them. Demo signals remain deterministically
auto-approved with an explicit audit event.
Demo evidence remains labeled separately, and reseeding demo records preserves
real provider payloads, normalized videos, topics, signals, and user actions.
The same review workspace shows per-comment relevance evidence and supports
audited accept/reject/model overrides. Admin → Providers exposes relevance
rejection rate and a deterministic replay action.

Comment-derived demand is integrated into the transparent signal score. Live
channel fit combines the owned channel profile, historical uploads, production
constraints, authority, timing, cannibalization, and brand-risk penalties.

The private-beta loop starts at
[Workspace Pulse](http://localhost:3000/pulse). Signals are tracked through
open, save/dismiss, brief, published outcome, and success. The
[Digest](http://localhost:3000/digest) turns the top three current signals into
a deterministic evidence report with Act/Watch/Skip guidance, source videos,
audience demand, saturation, timing, and a channel-specific angle.

For a new founder workspace, use the API setup endpoint and continue at
`/onboarding`. The complete first-workspace procedure is in the
[private-beta runbook](./docs/private-beta-runbook.md).

## Verification

```bash
make format
make lint
make typecheck
make migrate
make test
make test-e2e
make build
```

## Demo workflow

1. Filter the feed to Emerging signals.
2. Open a signal and inspect earlyness, score components, videos, comments, and
   freshness.
3. Save or dismiss the signal with a structured reason.
4. Create an evidence-linked content brief.
5. Link a published outcome.
6. Review the resulting funnel and north-star metric in Pulse.
7. Generate the top-three evidence digest.
8. Inspect health, failed jobs, and recovery point in Admin → Operations.
9. Inspect providers, discovery runs, immutable payloads, and replay in Admin →
   Providers.
10. Inspect evidence, risks, reviewer decisions, and audit history in Admin →
    Review.

See the [MVP specification](./CREATOR_TREND_INTELLIGENCE_SCRAPING_FIRST_MVP_CODEX_SPEC.md)
and [architecture decisions](./docs/decisions/). Production topology and
release steps are documented in [deployment](./docs/deployment.md); recovery
procedures are in [backup and recovery](./docs/backup-recovery.md).
