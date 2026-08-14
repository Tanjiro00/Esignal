# Operations

- `make setup` installs Python and web dependencies.
- `make demo` migrates and seeds the demo database, then starts API and web.
- `make service` starts API, web, and the real due-query scheduler.
- `make seed-demo` resets deterministic demo entities while preserving real
  ingestion queries, payloads, videos, and monitored channels.
- `make seed-queries` idempotently installs the initial AI/tech query universe.
- `make ingest-real` runs one live query through discovery, metadata, and
  normalization.
- `make run-ingestion` runs the currently due queries and channels once.
- `make refresh-video-intelligence` takes a fresh official metadata snapshot
  for recent real videos and rebuilds their features and channel baselines.
- `make run-snapshots` runs only currently due snapshot jobs once.
- `make build-signals` force-runs embedding, topic clustering, topic snapshots,
  scoring, and workspace signal generation for all currently eligible videos.
- `make refresh-demand` samples top and newest comments for up to 12 promising
  videos, classifies stored comments, rebuilds cross-video demand clusters, and
  updates signal scores.
- `make refresh-transcripts` fetches public captions for up to 8 high-value
  topic videos, stores timed evidence, and rebuilds transcript-aware topic
  embeddings.
- `make generate-digest` generates and stores the latest top-three report for
  the first configured workspace. Pass `WORKSPACE_ID=...` for an explicit
  workspace.
- `make backup` creates a database-consistent SQLite or PostgreSQL backup plus
  SHA-256 checksum.
- `make verify-backup` verifies the latest checksum and database structure.
- `make restore-backup BACKUP_FILE=/absolute/path/to/file` verifies, restores,
  and migrates the selected backup. Stop API and worker writers first.
- `make check` runs format checks, lint, type checks, unit/integration tests, and
  the production web build.
- `make test-e2e` runs the browser workflow against isolated demo services.

Demo reset is rejected unless `DEMO_MODE=true`.

Provider credentials live only in the ignored `.env` file. Never put them in
client-side environment variables, raw payloads, request fingerprints, logs,
fixtures, or commits. If a credential is pasted into a chat or issue, rotate it
before production use.

Raw provider payloads are stored under `var/raw_payloads/` as immutable gzip
JSON and are ignored by Git. Admin payload reads are restricted to that root
and the deterministic demo fixture root.

Admin → Operations, backed by
`GET /api/v1/admin/operations/readiness`, is the founder-facing readiness
surface. It reports:

- provider and budget alerts;
- the last discovery, topic, demand, and transcript run;
- the newest failed runs and snapshot jobs as a dead-letter queue;
- raw-payload storage availability;
- the newest backup age and checksum presence.

A `critical` state means a provider or budget condition can stop collection.
`degraded` means the product remains usable but has stale evidence, failed
jobs, missing payload storage, or an overdue backup. Review the job error,
repair the underlying provider/storage condition, and rerun the matching
one-shot command. Do not delete failed records: they are the audit trail.

The current public web parser uses no login, CAPTCHA solving, fingerprint
spoofing, or private data. Treat it as an MVP adapter: provider benchmarking and
a second fallback adapter are required before production routing is considered
complete.

The long-running worker schedules the `+30m`, `+1h`, `+3h`, `+6h`, `+12h`,
`+24h`, `+48h`, `+72h`, `+7d`, `+14d`, and `+30d` observations. It records
unobservable early targets as skipped using each video's discovery lag.
`GET /api/v1/admin/video-intelligence/metrics` exposes coverage, pending/due/
failed/skipped jobs, oldest-job lag, feature coverage, baseline coverage, and
latest snapshot freshness.

`GET /api/v1/admin/topic-intelligence/metrics` exposes source/eligible video
counts, embedding and assignment coverage, live topic/signal counts, stale
signals, clustering lag, and the latest pipeline run. A forced rebuild is also
available from Admin → Providers or
`POST /api/v1/admin/topic-intelligence/run?force=true`.

The long-running worker runs topic intelligence on startup and after discovery
or snapshot work changes stored evidence. Repeated runs use stable topic and
signal IDs; every completed calculation still appends an immutable topic
snapshot for auditability.

`GET /api/v1/admin/demand-intelligence/metrics` exposes sampled-video coverage,
stored/classified comment counts, confirmed clusters, topics with demand,
provider failures, comments-disabled videos, and processing lag. Admin →
Providers can force the same pipeline through
`POST /api/v1/admin/demand-intelligence/run`.

Comment fetches use a 12-hour idempotency bucket by default and separately
sample relevance-ordered and time-ordered comments. The worker uses configured
provider priority and falls back from `youtube_official` to
`youtube_web_comments`. Durable payloads exclude author display names, profile
images, and public channel identifiers; only a one-way author hash is retained
to verify independent commenters.

`GET /api/v1/admin/transcript-intelligence/metrics` exposes selected-video
coverage, native/auto-caption counts, segment/evidence counts, covered topics,
unavailable videos, failures, and processing lag. Admin → Providers can force
the same pipeline through `POST /api/v1/admin/transcript-intelligence/run`.

Transcript fetches are stable and idempotent per video, language policy, and
processing version. Public native captions are preferred; YouTube
auto-captions are the fallback. The worker does not download video or generate
audio transcripts. Missing captions are recorded as unavailable and never stop
signals based on metadata, snapshots, comments, and topic evidence. Raw
transcript payloads remain server-side; Admin and product APIs redact the full
text and return only bounded evidence excerpts.

## Private-beta service checks

After every deploy:

```bash
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8000/api/v1/admin/operations/readiness
docker compose -f docker-compose.production.yml ps
docker compose -f docker-compose.production.yml logs --tail=200 api worker
```

Then open Pulse, Digest, one signal, Admin → Operations, and Admin → Providers.
Confirm the web origin can call the API, a digest has exactly three evidence
items when three signals are available, and no secret appears in browser
responses or logs.

## Incident sequence

1. Pause external traffic or the worker if writes could worsen the failure.
2. Capture `docker compose ... ps`, API/worker logs, Operations JSON, current
   Alembic revision, and provider routing decisions.
3. For provider incidents, disable only the failing capability or reset its
   circuit after the upstream recovers.
4. For data corruption, stop API and worker, preserve the current database, and
   follow the recovery runbook.
5. Run the affected pipeline once, verify evidence freshness, then resume the
   worker and traffic.
6. Record cause, time window, affected workspaces, recovery point, and any
   credentials rotated.

For production release order, rollback, and proxy/TLS requirements, see
[deployment](./deployment.md). For RPO/RTO and restore drills, see
[backup and recovery](./backup-recovery.md).

## Upstream dependency advisory

As of 2026-07-27, the latest stable Next.js release (`16.2.12`) installs nested
PostCSS `8.4.31` and optional Sharp `0.34.5`, which npm flags under current
high-severity advisories. Slice 1 does not process user-supplied CSS and does not
use Next image optimization, so those vulnerable paths are not exposed by the
demo. Upgrade Next.js as soon as a stable release carries patched nested
versions; do not use `npm audit fix --force`, which currently proposes an
incompatible downgrade.
