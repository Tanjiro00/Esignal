# Data provenance

Every demo signal references stored videos, comments, snapshots, topic
memberships, and mock provider fetches. Mock raw payloads live in
`fixtures/demo/raw_payloads/`; fetch rows store their immutable SHA-256 hash and
request fingerprint.

All demo entities use deterministic UUIDv5 IDs. Resetting demo data reproduces
the same evidence graph and makes replay assertions stable.

Real provider responses are persisted before normalization as content-addressed
gzip JSON under `var/raw_payloads/`. Each `provider_fetches` row records:

- a secret-free deterministic request fingerprint;
- provider, capability, and endpoint;
- immutable SHA-256 content hash and storage URI;
- latency, HTTP status, parser version, and estimated/actual cost;
- linked external and normalized entity IDs.

`field_provenance` stores one value hash per normalized field observation.
`raw_payload_links` connects a fetch to every entity it supports.
`video_discovery_occurrences` preserves query rank and discovery history while
`youtube_videos.youtube_video_id` remains the global canonical deduplication
key.

The admin fetch explorer can inspect both fixture and compressed live payloads.
Replay reuses the stored payload hash and records zero provider cost.
