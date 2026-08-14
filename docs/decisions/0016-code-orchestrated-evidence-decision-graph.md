# ADR 0016: Code-orchestrated evidence decision graph

Status: accepted

## Context

EarlySignal needs LLM assistance for precise microtrend naming, semantic
reconciliation, evidence-grounded explanations, and channel-specific content
gaps. A free-form multi-agent swarm would make publication decisions difficult
to reproduce, budget, validate, and debug.

The application already owns normalized YouTube evidence, deterministic scores,
stable topic identity, channel-fit logic, and content-gap ranking.

## Decision

Use an application-managed directed graph built on bounded Responses API calls.
Each model step has a strict output schema and an evidence allowlist.

The graph has three generative specialist tasks:

- taxonomy adjudication;
- actionable-topic synthesis;
- channel-specific content-gap synthesis.

Topic and content-gap synthesis must pass a separate grounding verifier before
the application releases them. The verifier can only accept or reject targets;
it cannot rewrite the artifact or change deterministic values.

The application remains authoritative for routing, budgets, retries, circuit
breaking, caching, persistence, release gates, and fallback.

Only deterministic-actionable topics receive per-topic LLM synthesis.
Every failure path returns deterministic output.

The graph policy and step decisions are traced on `TopicPipelineRun`; detailed
model calls remain in `LLMIntelligenceRun`.

## Consequences

Positive:

- deterministic scores and evidence stay authoritative;
- model failures do not stop the pipeline;
- unsupported output is rejected before publication;
- calls are idempotent, bounded, cached, and auditable;
- individual tasks can be evaluated and routed independently.

Tradeoffs:

- successful synthesis normally needs a second verifier call;
- a same-model verifier is not fully independent;
- application-managed orchestration requires explicit contracts and routing;
- shadow evaluation is required before enabling visible LLM output.

## Agents SDK boundary

Do not introduce the Agents SDK into the batch pipeline yet. Reconsider it for
an interactive analyst with multi-turn state, read-only tools, approvals, and
observable handoffs. Batch topic intelligence benefits more from explicit
application-controlled branching.
