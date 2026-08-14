# ADR 0021: Editable, duration-consistent producer briefs

Status: accepted

## Context

The Briefs page previously rendered a read-only handoff with one “Suggested
structure” list. Its first three rows described the opening through `1:20`, but
the final row switched to the vague label `1:20 onward`. That did not match the
stored recommendation for an 18–24 minute video and left the producer without
an actionable full-video plan.

The page also lacked the working metadata and proof controls needed to move a
recommendation into production. The post-audit plan requires a distinct
suggested opening, a duration-consistent full outline, editable producer fields,
and a required-proof checklist.

## Decision

The brief keeps the original evidence-grounded `ContentAngle` and extends its
existing `brief_json` document with producer-owned fields:

- `owner`;
- `target_publish_date`;
- `audience_takeaway`;
- `required_proof_checklist`;
- `production_notes`;
- `suggested_opening`;
- `full_outline`;
- `brief_document_version`.

No schema migration is needed. The existing brief title and status remain
first-class database fields. Saving uses the existing typed
`PATCH /api/v1/workspaces/{workspace_id}/briefs/{brief_id}` contract and merges
the editor state into the current document so stored claims, evidence
references, content gaps, and packaging are preserved.

The suggested opening has three fixed, continuous time ranges ending at `1:20`:

1. `0:00–0:20`;
2. `0:20–0:45`;
3. `0:45–1:20`.

The full outline has seven fixed, continuous ranges ending at `23:00`:

1. `0:00–1:20` — Hook and setup;
2. `1:20–3:00` — Evaluation criteria and constraints;
3. `3:00–10:00` — Real workflow test;
4. `10:00–14:00` — Failures and recovery;
5. `14:00–18:00` — Guardrails and trade-offs;
6. `18:00–21:00` — Results;
7. `21:00–23:00` — Recommendation.

“Evaluation criteria and constraints” is used instead of the narrower
“Permissions and safety criteria” from the example plan. It preserves the same
editorial purpose while remaining valid for non-agent signals such as product
comparisons, coding tools, model releases, and hardware tests.

Producers can edit the labels but not the time boundaries. This keeps the brief
adaptable without allowing accidental gaps, overlaps, or a runtime mismatch.
The working title, owner, publish date, status, audience takeaway, proof items,
proof completion, and production notes are editable. Copy and Markdown export
are generated from the current stored document.

The brief remains a producer handoff. It does not generate a full script and
does not create new factual claims.

## Consequences

- The opening and full video structure are visibly distinct.
- Every default producer field is derived from stored brief, packaging,
  workspace, or publishing-window data.
- Evidence-grounded angle data survives every editor save.
- Timeline consistency is deterministic and independent of an LLM.
- Existing brief rows remain compatible because missing producer fields are
  derived at read time and persisted only after the first save.
- Fixed boundaries trade freeform runtime editing for predictable production
  handoffs in this slice.

## Verification

Unit coverage verifies the three-step opening, seven-step continuous outline,
23-minute runtime, immutable defaults, producer-field derivation, and
evidence-preserving save merge.

End-to-end coverage verifies creation from Today, read mode, editor controls,
proof completion, save persistence, transition to production, and a
390×844 mobile layout without horizontal overflow.

Desktop and mobile read/editor captures are stored under
`docs/post-audit-slice-5/screenshots/`.

## Rollback

Restore the previous Briefs page and remove the producer-document helper and
editor component. Existing database rows require no rollback because the added
keys live inside backward-compatible JSON and the original `ContentAngle`
fields are preserved.
