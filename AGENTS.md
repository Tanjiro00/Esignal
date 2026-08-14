# EarlySignal contribution rules

This repository implements the scraping-first Creator Trend Intelligence MVP. The
root specification is authoritative; where it conflicts with older documents,
`CREATOR_TREND_INTELLIGENCE_SCRAPING_FIRST_MVP_CODEX_SPEC.md` wins.

## Scope

- YouTube only; English-language AI/technology content only.
- Current delivery boundary: the implementation slice explicitly requested by
  the user. Do not pull later-slice features forward without documenting the
  reason.
- No billing, other social platforms, full script generation, automatic
  publishing, or end-user provider configuration.
- Demo mode must work without credentials and remain visibly isolated from
  production data.

## Data and evidence

- Keep provider response shapes behind typed provider interfaces.
- Deduplicate with canonical YouTube `video_id` and `channel_id`.
- Preserve raw payload references, field provenance, and historical snapshots.
- Every visible claim, quote, score, and recommendation must resolve to stored
  demo or provider evidence. Never invent evidence in application logic.
- LLMs may summarize stored evidence but may not set deterministic trend scores.
- Store only the minimum commenter data needed for clustering and evidence.

## Reliability and security

- Providers must degrade gracefully; retries, health, cost, and circuits are
  domain concerns even when Slice 1 uses mocks.
- Do not implement CAPTCHA solving, fingerprint spoofing, credential pooling,
  private/login-only scraping, or storage of full videos.
- Keep credentials server-side, sanitize logs, and expose no raw secrets.

## Engineering

- Keep the monorepo runnable after every slice.
- Maintain stable typed API contracts under `/api/v1`.
- Jobs and demo mutations must be deterministic and idempotent.
- Add tests for behavior changed in each slice.
- Before handoff run `make format`, `make lint`, `make typecheck`,
  `make migrate`, `make test`, and `make test-e2e`.

