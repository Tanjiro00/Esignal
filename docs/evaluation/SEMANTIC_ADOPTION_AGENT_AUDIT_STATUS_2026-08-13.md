# Semantic adoption agent audit — production status

Recorded: 2026-08-13.

## Frozen inputs

- Prospective cohort remains outcome-embargoed through 2026-09-24.
- Release queue v2 SHA-256:
  `19f2fded971a2f86a6ffae11567e2e2bfc9481f8ed03cee75b6d5b26d1e9d48f`.
- Frozen top-quintile candidates: 32.
- Deterministic evidence abstentions: 9.
- Eligible for the three-role shadow audit: 23.
- Product-release-ready candidates: 0.

## Production verification

The release queue and protocol hashes on the production host match their
locally frozen files. The production image successfully imports the API and
worker and exposes the supported module entrypoint:

```text
python -m scripts.audit_semantic_release_queue
```

A zero-candidate production dry run completed with:

- 9 `abstained_deterministic_pre_audit`;
- 23 `not_processed_batch_limit`;
- 0 product releases;
- output SHA-256
  `30d2036cbe14366e8d7a535071ea8f3f413cdaec7e1eda22676ff4fab9737b25`.

A one-candidate budget-guard run completed with:

- one `evidence_analysis_unavailable` result;
- trace decision `skipped_daily_token_budget`;
- no change to persisted rolling token usage;
- 0 product releases;
- output SHA-256
  `7b1bd1040a3a780cdae139e12ee847f2a3ec7448c549e2cee54d45a697d7dd86`.

## Current execution gate

At the production check, successful or rejected stored LLM runs consumed
1,005,787 tokens in the rolling 24-hour window against the configured
1,000,000-token hard cap. The excess came from runs created before the new
task-budget routing was deployed. The audit correctly abstained instead of
bypassing the cap.

The global cap first drops below its limit at approximately
2026-08-14 15:34:28 UTC (18:34:28 Europe/Moscow). Approximately 100,000 tokens
of global headroom become available at 2026-08-14 15:37:59 UTC
(18:37:59 Europe/Moscow), assuming no intervening LLM consumption.

No automatic paid run is scheduled by this status record. Before the real
batch starts, re-read both the global rolling usage and the topic-task-group
usage. Run a bounded batch, preserve every role output and evidence reference,
and keep every decision shadow-only.

## Validation completed

- `make format`
- `make lint`
- `make typecheck`
- `make migrate`
- `make test`: 295 Python and 36 web tests passed
- `make test-e2e`: 15 browser tests passed
- Production preflight passed against the exact built API and worker images
- Production HTTPS landing and health endpoints returned HTTP 200
