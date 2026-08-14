# Architecture

```text
Next.js web ──typed HTTP──> FastAPI ──SQLAlchemy──> SQLite / PostgreSQL
                                      │
                                      ├─provider SDK──> youtube_web
                                      │                 ├─public search
                                      │                 └─channel RSS
                                      │
                                      ├─provider SDK──> youtube_official metadata
                                      └─raw store─────> gzip JSON by content hash

Scheduler CLI ──due query/channel jobs──> ingestion service
                                           ├─raw evidence first
                                           ├─canonical global deduplication
                                           ├─normalized video/channel upserts
                                           ├─field provenance + cost/health
                                           └─availability-aware snapshot jobs
                                                        │
                                                        ├─immutable counters
                                                        ├─channel baselines
                                                        └─velocity/outlier features
```

Product code consumes normalized evidence contracts. Provider fetch details are
available only through admin endpoints. Demo seeding uses deterministic UUIDv5
identifiers and never calls the network. The real ingestion path is
provider-independent and does not make the official YouTube search API a
discovery prerequisite.

Snapshot jobs are keyed by canonical video and target age. Targets that predate
discovery are recorded as skipped instead of fabricating measurements.
Successful observations remain immutable and keep the provider fetch that
supports them. Versioned feature and baseline rows can be rebuilt from stored
snapshots without changing provider contracts.
