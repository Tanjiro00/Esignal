# ADR 0024: Raw mirror / derived store split

## Status

Accepted. The initial storage boundary and write path are implemented; expiry
enforcement and replay consumers remain follow-up work.

## Context

YouTube API Data and EarlySignal's own derived analysis previously lived side
by side without a structural boundary. That made retention policy and audit
provenance ambiguous, and made it too easy for later scoring code to read raw
provider payloads directly.

The implementation plan also requires raw provider responses to be retained
before processing so the pipeline can be replayed without spending quota a
second time.

## Decision

Introduce two explicit storage layers:

- `raw_api_snapshots` mirrors official YouTube Data API responses. Each row is
  stamped with provider, provenance, fetch time, and a 30-day expiry.
- `derived_metric_points` is an append-only ledger of EarlySignal-computed
  values. Every point carries its subject, metric, window, computation time,
  scoring version, and a fingerprint of its inputs.

`apps/api/derived_store.py` is the write boundary. The video-intelligence worker
records official metadata snapshots and projects channel baselines and video
features into the derived ledger. Scoring, channel fit, clustering, and replay
must not read `raw_api_snapshots` directly; a regression test enforces that
package boundary.

The existing `VideoSnapshot`, `ChannelBaseline`, and `VideoFeature` tables stay
in the live path for now. This slice adds an auditable parallel ledger without
changing current recommendation behavior.

## Consequences

- Raw provider data and product-owned analysis now have different schemas and
  can have different retention policies.
- New computed metrics start accumulating a reproducible history for replay and
  backtesting.
- Existing feature/baseline history needs an idempotent one-off backfill.
- A later retention job must enforce `expires_at`; a later replay slice must
  switch reads from mutable current-state tables to the immutable ledger.
