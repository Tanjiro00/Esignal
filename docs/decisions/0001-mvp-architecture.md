# ADR 0001: MVP architecture

- Status: Accepted
- Date: 2026-07-26
- Scope: Slice 1 — Foundation and demo

## Context

EarlySignal needs a credible private-beta loop before it needs global scale. It
must be demoable without credentials, but the demo must exercise the same
contracts and persistence boundaries that later provider-backed slices will use.

## Decision

Use a small monorepo with:

- `apps/web`: Next.js, React, TypeScript, Tailwind CSS, TanStack Query, and
  lightweight SVG charts.
- `apps/api`: FastAPI, Pydantic v2, SQLAlchemy 2, and Alembic.
- `apps/worker`: a reserved Python entrypoint for later background jobs.
- `packages/domain`: provider-independent dataclasses and enums.
- `packages/provider_sdk`: typed provider protocols, routing skeleton, and Slice
  1 mock adapters.
- PostgreSQL and Redis in Docker Compose. SQLite is the credential-free default
  for local demo and tests; the same SQLAlchemy models run against PostgreSQL.

The API owns demo persistence. The web application uses `/api/v1` contracts and
never imports provider payloads. Demo authentication is an explicit bypass,
enabled only when `DEMO_MODE=true`.

## Consequences

- A new contributor can run the complete product with `make demo`.
- SQLite makes the first demonstration fast, while Docker Compose verifies the
  target PostgreSQL/Redis topology.
- The worker boundary exists without prematurely implementing the ingestion
  pipeline.
- Schema growth must continue through Alembic; demo fixtures are code-generated
  deterministically instead of hand-maintained database dumps.

## Rejected alternatives

- Frontend-only static fixtures: they would not validate the action and outcome
  loop or migration path.
- A single Next.js full-stack service: it would blur Python provider/worker
  boundaries required by later slices.
- ClickHouse: PostgreSQL is sufficient until a measured bottleneck exists.

