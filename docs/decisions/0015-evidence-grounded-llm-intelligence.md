# ADR 0015: Evidence-grounded LLM intelligence

## Status

Accepted for the user-requested implementation slice. Disabled by default until
the server-side OpenAI credential is configured.

## Context

The deterministic pipeline can identify and rank emerging YouTube topics, but
rule-based labels and opportunity text are often mechanical. The requested
quality improvements are:

- precise microtrend names;
- reconciliation of equivalent formulations;
- evidence-backed explanations of why a trend is growing;
- more specific creator content gaps.

The root specification also requires every visible claim to resolve to stored
evidence and prohibits an LLM from setting deterministic trend scores.

## Decision

Use the OpenAI Responses API with strict Structured Outputs as an optional
editorial layer after deterministic retrieval and candidate generation.

The LLM receives a bounded evidence packet containing only stored video,
snapshot, transcript-segment, and representative-comment records. It returns
only typed fields with exact `evidence_refs`.

The application validates:

- every evidence reference exists in the supplied packet;
- topic reconciliation is a complete partition with no duplicate candidates;
- different products, facets, or domains are never merged by the LLM;
- content-gap keys are preserved exactly;
- generic topic labels are rejected;
- score, rank, timing, feasibility, and lifecycle fields are never accepted
  from model output.

Every invocation is idempotently cached in `llm_intelligence_runs` with input
hash, prompt version, provider, model, output, validation result, token usage,
latency, and error status. API failures, invalid outputs, missing credentials,
call limits, or an open circuit degrade to the deterministic pipeline.

OpenAI response storage is disabled with `store: false`. Credentials remain
server-side.

## Model roles

The default is configurable and starts with `gpt-5.6-terra` for the balanced
structured synthesis workload. A later evaluation may route:

- high-volume extraction or classification to Luna;
- ordinary topic and gap synthesis to Terra;
- difficult conflict resolution or audit to Sol.

Model routing must be justified by measured quality, latency, and token usage.

## Agent boundary

The first release uses bounded single-purpose structured calls. Multi-agent
orchestration is not enabled automatically. It will be evaluated separately
for high-value topics where parallel evidence analysis and adversarial review
can improve quality enough to justify extra tokens and complexity.

## Consequences

- Production behavior is unchanged until both the feature flag and credential
  are present.
- User-visible LLM claims can link back to stored evidence.
- Scores remain reproducible and comparable across model or prompt upgrades.
- Prompt and model changes become auditable and evaluable.
- LLM quality can improve presentation and synthesis without weakening the
  evidence contract.

## Official API references

- [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs)
- [GPT-5.6 prompting guidance](https://developers.openai.com/api/docs/guides/prompt-guidance-gpt-5p6)
- [Responses API Multi-agent beta](https://developers.openai.com/api/docs/guides/responses-multi-agent)
