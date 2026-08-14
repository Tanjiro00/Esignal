# ADR 0002: Provider abstraction and demo routing

- Status: Accepted
- Date: 2026-07-26
- Scope: Slice 1 — Foundation and demo

## Context

Discovery, metadata, comments, and transcripts will come from replaceable
providers with different schemas, cost, latency, and failure behavior. Product
logic cannot depend on any provider-specific response.

## Decision

Define immutable provider-independent request/result dataclasses and Python
`Protocol` interfaces for:

- discovery;
- video metadata;
- channels;
- comments;
- transcripts.

A capability router receives ordered adapters and returns normalized domain
objects. Slice 1 ships deterministic mock adapters for every capability. Each
mock call creates a fetch record with a request fingerprint, content hash, cost,
latency, parser version, and raw fixture reference.

The router API is stable now; retries, circuits, budgets, and real-provider
fallback are extended in later slices without changing product services.

## Invariants

- Provider-native keys do not cross the SDK boundary.
- Canonical YouTube IDs are the global deduplication keys.
- Raw references are written before normalized entities are used.
- Visible evidence always names stored entity IDs.
- Demo provider and production provider data never share a database.

## Consequences

Mocks test the real interface instead of bypassing it. Real adapters can be
benchmarked and replaced without changing signal scoring or UI contracts.

