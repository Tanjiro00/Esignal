# EarlySignal improvement baseline — Slice 0

- Status: Accepted baseline
- Date: 2026-07-28
- Scope: Product improvement Slice 0 — baseline and safety
- Product behavior changed: No
- Next slice started: No

## 1. Purpose

This decision freezes the behavior and safety state that existed before the
EarlySignal decision-quality improvement program.

The baseline is intended to answer four questions:

1. What does the current demo produce deterministically?
2. What did production contain at a known point in time?
3. Which model versions produced those records?
4. Can the production database be backed up, verified, restored, and migrated?

Authoritative inputs:

- [`CREATOR_TREND_INTELLIGENCE_SCRAPING_FIRST_MVP_CODEX_SPEC.md`](../../CREATOR_TREND_INTELLIGENCE_SCRAPING_FIRST_MVP_CODEX_SPEC.md)
- [`PLATFORM_CURRENT_STATE_RU.md`](../PLATFORM_CURRENT_STATE_RU.md)
- `EARLYSIGNAL_PRODUCT_IMPROVEMENT_CODEX_PLAN_RU.md`, supplied for this
  implementation outside the repository
- [`0001-mvp-architecture.md`](./0001-mvp-architecture.md)
- [`0002-provider-abstraction.md`](./0002-provider-abstraction.md)

## 2. Slice 0 boundaries

This slice does:

- freeze demo and live topic/signal behavior as JSON regression fixtures;
- record current code and observed data-model versions;
- add typed rollout flags for later slices, all disabled by default;
- pin accepted visual QA artifacts by path, dimensions, and SHA-256;
- verify migrations from a clean SQLite database;
- create and verify a PostgreSQL production backup;
- complete an isolated restore drill;
- document known drift and blockers.

This slice does not:

- change scoring weights or hard gates;
- change signal visibility;
- redesign user-facing UI;
- add providers;
- add lifecycle history, review, relevance, packaging, OAuth, or query
  expansion;
- modify production application code or restart production services;
- delete historical or demo-tagged records from production;
- begin Slice 1.

## 3. Repository baseline

The repository currently contains all original MVP slices 1–10:

- deterministic demo mode;
- provider abstraction, raw payloads, and provenance;
- YouTube discovery and metadata ingestion;
- snapshots, baselines, and video features;
- microtopics, topic measurements, scoring, and visible signals;
- comments and demand clusters;
- public transcript enrichment;
- provider retry, circuit, cost, and routing controls;
- Channel Fit, opportunities, briefs, and outcomes;
- onboarding, digest, product analytics, operations, backup, and deployment.

Runtime boundaries remain:

| Layer | Current implementation |
| --- | --- |
| Web | Next.js 16, React 19, TypeScript |
| API | FastAPI, Pydantic, SQLAlchemy |
| Worker | Single Python worker with deterministic/idempotent runs |
| Production data | PostgreSQL 17, Redis AOF, raw payload volume |
| Local/demo data | SQLite and deterministic seeded entities |
| Stable API prefix | `/api/v1` |

## 4. Current model versions

These are the versions imported by the current code at Slice 0:

| Domain | Version |
| --- | --- |
| Video features | `video-intelligence-v1` |
| Channel baseline | `channel-baseline-v1` |
| Video embedding | `video-embedding-v2-transcript` |
| Embedding model | `local-hashing-title-entity-transcript-v2` |
| Microtopic clustering | `live-microtopic-clustering-v4` |
| Early Signal Score | `early-signal-score-v3-quality` |
| Comment demand classifier | `comment-demand-rules-v2` |
| Demand clustering | `demand-intent-clustering-v2` |
| Transcript processing | `transcript-processing-v2` |
| Channel Fit | `channel-fit-v1` |
| Digest | `evidence-digest-v1` |

The production database also retains rows created by older or demo versions.
The fixture records those values under `model_versions.observed`; they are not
silently rewritten to current versions. Examples include clustering v2/v3,
comment rules v1, and demo records. This is intentional audit history.

## 5. Rollout feature flags

Slice 0 adds typed flags to `Settings`. Every default is `false`, and current
product code does not consume any of them yet.

| Environment variable | Later capability |
| --- | --- |
| `FEATURE_EARLYNESS_TIMELINE` | Slice 1 earlyness and lifecycle history |
| `FEATURE_SIGNAL_REVIEW_QUEUE` | Slice 2 review queue |
| `FEATURE_COMMENT_TOPIC_RELEVANCE` | Slice 3 semantic relevance |
| `FEATURE_DECISION_EXPERIENCE` | Slice 4 decision card and score buckets |
| `FEATURE_MICROTOPIC_CONTENT_GAP` | Slice 5 microtopics v5/content gap |
| `FEATURE_FEEDBACK_EVALUATION` | Slice 6 feedback/evaluation |
| `FEATURE_TOPIC_SNAPSHOT_BUCKETS` | Time-bucket aggregation |
| `FEATURE_CHANNEL_PROFILE_FEASIBILITY_V2` | Slice 7 profile/feasibility |
| `FEATURE_OUTCOME_SUGGESTIONS` | Slice 8 outcome automation |
| `FEATURE_SIGNAL_PACKAGING` | Slice 9 packaging |
| `FEATURE_YOUTUBE_OAUTH_ANALYTICS` | Slice 10 OAuth analytics |
| `FEATURE_QUERY_EXPANSION` | Slice 11 query expansion |

The values are documented in `.env.example` and
`.env.production.example`. Enabling a flag before its corresponding
implementation exists has no effect.

## 6. Deterministic evaluation fixtures

### 6.1 Production point-in-time fixture

File:

- [`current-production-snapshot.json`](../../fixtures/evaluation/current-production-snapshot.json)

Source:

- verified production backup
  `earlysignal-20260728T080656Z.dump`;
- captured at `2026-07-28T08:06:56Z`;
- Alembic revision `e52c91ab74d0`;
- `source_kind=live` only.

Counts:

| Metric | Value |
| --- | ---: |
| Active live topics | 10 |
| Active visible live signals | 2 |
| Evidence memberships in exported active topics | 80 |
| Demand clusters attached to exported topics | 6 |
| Workspace signal-score records | 2 |

The improvement plan expected 9 topics and 2 signals because
`PLATFORM_CURRENT_STATE_RU.md` captured production around 07:16 UTC. The worker
formed another active topic before the verified 08:06 backup. The regression
fixture uses the observed 10/2 state instead of falsifying the current
baseline.

Exported topics:

| Topic | Stage | User-visible | Videos | Channels |
| --- | --- | --- | ---: | ---: |
| Beginner and no-code AI agents | Breakout | Yes | 11 | 8 |
| Beginner and no-code Developer tools | Seed | No | 4 | 3 |
| Free, local and unlimited AI agents | Emerging | No | 3 | 3 |
| Free, local and unlimited AI video generation | Emerging | Yes | 26 | 8 |
| Free, local and unlimited Claude ai models | Seed | No | 6 | 3 |
| Free, local and unlimited Productivity | Declining | No | 4 | 4 |
| Open-source AI models | Seed | No | 4 | 4 |
| Security failures in OpenAI ai models | Saturated | No | 8 | 8 |
| Task-specific AI agents | Seed | No | 8 | 4 |
| Task-specific Claude Code ai agents | Declining | No | 6 | 3 |

Visible signal values at capture:

| Signal | Stage | Score |
| --- | --- | ---: |
| Beginner and no-code AI agents | Breakout | 75.4 |
| Free, local and unlimited AI video generation | Emerging | 71.3 |

Fixture SHA-256:

```text
7bddafe36692b749c9d54559a7112183f6c86b62a386be5d6540aa5f276af3e8
```

### 6.2 Demo fixture

File:

- [`current-demo-snapshot.json`](../../fixtures/evaluation/current-demo-snapshot.json)

The deterministic demo contains:

| Metric | Value |
| --- | ---: |
| Topics | 5 |
| Signals | 5 |
| Evidence memberships | 60 |
| Demand clusters | 5 |
| Workspace signal-score records | 5 |

Fixture SHA-256:

```text
1118cbc7b260cab08759e07b46c2d11203068471a48e3f6106409cfd2da7e579
```

### 6.3 Privacy and reproducibility

Both fixtures:

- retain stable topic, signal, video, channel, evidence, and workspace IDs;
- retain point-in-time scores, components, model versions, and opportunities;
- sort topics, memberships, demand records, and workspace scores
  deterministically;
- carry their own canonical content SHA-256;
- contain no raw comment text;
- contain no commenter hashes;
- contain no raw provider payloads;
- contain no credentials.

The exporter is:

```text
scripts/export_evaluation_snapshot.py
```

It accepts an explicit capture timestamp and expected topic/signal counts so a
moving production worker cannot silently produce a different fixture.

## 7. Visual baseline

The manifest is:

- [`baseline-screenshots.json`](../../fixtures/evaluation/baseline-screenshots.json)

It pins three previously accepted deterministic demo QA artifacts:

| Surface | Dimensions | Artifact |
| --- | ---: | --- |
| Signals desktop | 1440×1024 | `docs/redesign-qa/final-1440x1024.png` |
| Signals mobile selected | 390×844 | `docs/redesign-qa/final-mobile-selected-390x844.png` |
| Signal detail tablet | 740×755 | `docs/redesign-qa/detail-740x755.png` |

Each artifact is resolved and checksum-verified by the regression test. A fresh
localhost capture was attempted but rejected by the browser URL policy; no
alternate browser surface was used to bypass that restriction.

Production behavior is not inferred from these demo images. It is pinned by
the production JSON fixture.

## 8. Production operational snapshot

Read-only audit at `2026-07-28T08:16:01Z`:

| Metric | Value |
| --- | ---: |
| YouTube videos | 1,532 |
| Videos with snapshots | 1,532 |
| Snapshot records | 4,325 |
| Channel baseline records | 930 |
| Video feature records | 1,232 |
| Active live topics | 10 |
| Active live signals | 2 |
| All current topic memberships | 140 |
| Video embeddings | 832 |
| Stored comments | 2,399 |
| Demand clusters | 11 |
| Topics with demand | 8 |
| Transcripts | 22 |
| Transcript segments | 548 |
| Evidence transcript segments | 70 |
| Signal actions | 2 |
| Briefs | 1 |
| Published outcomes | 1 |
| Product events | 74 |

The numbers after 08:06 are operational state, not fixture inputs. Continuous
worker activity is expected to make them change.

At the same audit:

- API, PostgreSQL, and Redis were healthy;
- web and worker were running;
- production used `DEMO_MODE=false`;
- PostgreSQL was at Alembic head `e52c91ab74d0`.

## 9. Backup and migration safety

### 9.1 Production backup

Verified backup:

```text
/opt/earlysignal/backups/earlysignal-20260728T080656Z.dump
size: 6,871,872 bytes
checksum: OK
pg_restore --list: OK
```

The host also retained earlier backups from 2026-07-27 16:30 UTC and
2026-07-28 03:17 UTC.

Scheduled backup:

```text
/etc/cron.d/earlysignal-backup
17 3 * * * root /opt/earlysignal/scripts/production_backup.sh
```

The cron service was active and its latest scheduled log recorded a verified
backup. Off-host replication and 30-day retention are not proven by this
slice.

### 9.2 Isolated restore drill

The 08:06 backup was restored into a disposable PostgreSQL 17 container. The
temporary database reported:

```text
Alembic revision: e52c91ab74d0
active live topics: 10
active live signals: 2
```

The container was removed after the check. No production database or service
was mutated by the restore drill.

### 9.3 Migration safety

Migration validation now covers:

- production PostgreSQL already at head;
- a restored production backup readable at head;
- a clean SQLite database upgraded from base to head;
- explicit schema assertions that:
  - `youtube_channels.view_count` is `BIGINT`;
  - `signals.evidence_version` supports length 120;
- the existing E2E boot path, which creates a fresh isolated SQLite database
  and runs every migration.

Slice 0 adds no schema migration and no data backfill.

## 10. Behavior baseline tests

The committed tests assert:

- all improvement flags default to off;
- flags are independently configurable;
- the demo export is deterministic for a fixed capture time;
- demo and production fixtures have the expected source mode and counts;
- fixture content hashes are valid;
- fixtures exclude raw comments, commenter hashes, provider payloads, and
  secrets;
- visual baseline paths resolve to unchanged SHA-256 values;
- a clean SQLite database reaches Alembic head with the expected column types.

Existing integration, contract, frontend, and E2E tests remain the baseline for
the current product behavior.

Required Slice 0 verification completed successfully:

| Check | Result |
| --- | --- |
| `make format` | Passed |
| `make lint` | Passed |
| `make typecheck` | Passed |
| `make migrate` | Passed |
| Python tests | 50 passed |
| Frontend tests | 4 passed |
| Browser E2E | 4 passed |

The Python suite reports one existing Starlette `TestClient` deprecation
warning; it does not fail the suite.

## 11. Known limitations and blockers

### Before Slice 1

There is no hard implementation blocker for lifecycle history, but Slice 1
must:

1. remain behind `FEATURE_EARLYNESS_TIMELINE=false` until its backfill and UI
   acceptance tests pass;
2. use immutable historical measurements and never infer a transition from
   future evidence;
3. define the large-channel threshold and transition reason codes explicitly;
4. create a new verified pre-migration production backup;
5. compare output against the committed 10/2 point-in-time fixture;
6. preserve additive `/api/v1` compatibility.

### Operational follow-ups

- Prove off-host backup replication and retention; host-local backups alone do
  not meet the runbook.
- Decide whether retained demo-tagged rows in the production database should be
  migrated to a separate store. Slice 0 does not perform that destructive
  cleanup.
- Recapture the visual baseline when localhost browser access is available.
- Treat production counts as time-dependent. Never update the committed
  baseline without a new capture timestamp, verified backup, and fixture hash.

## 12. Slice 0 acceptance review

| Requirement | Result |
| --- | --- |
| Verify repository against current-state doc | Complete |
| Deterministic demo regression fixture | Complete |
| Current production regression fixture | Complete; actual baseline is 10/2 |
| Current model versions documented | Complete |
| Later-slice feature flags added | Complete; all off |
| Backup created and verified | Complete |
| Isolated restore drill | Complete |
| Migration safety verified | Complete |
| Baseline screenshots recorded | Complete via checksum manifest |
| Product behavior unchanged | Confirmed by design and regression suite |
| Slice 1 started | No |

Decision: Slice 0 is complete. Do not begin Slice 1 without a separate
implementation turn.
