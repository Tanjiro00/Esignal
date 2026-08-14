# Visual fidelity ledger

QA date: 2026-07-27

Browser verification used the in-app browser at 1536×1024 and 390×844.
Concepts and implementation renders are stored together under
`docs/design-concepts/`.

| Comparison point | Concept evidence | Render evidence | Result |
|---|---|---|---|
| Information architecture | Quiet app shell, Signals/Watchlists/Briefs/Outcomes/Settings, admin Providers | Same labels, order, selected state, and demo identity | Matched |
| Container model | Open lists and tables, hairline rules, no decorative KPI grid | Feed rows, evidence table, provider/fetch tables and research sections use open rules | Matched |
| Palette and typography | Cool white canvas, charcoal/slate, lime growth, coral risk, editorial research headings | Exact token roles implemented globally; serif is limited to page/research headings | Matched |
| Feed density | Topic, stage rail, score, fit, timing, momentum, channel/video counts, demand, sparkline, actions | All required fields and four actions fit at 1536×1024 after column-width repair | Matched |
| Detail hierarchy | Thesis, lifecycle, why emerging, evidence table, diffusion, demand, fit, saturation, opportunities, score rail | Same hierarchy; lower research sections continue below the first viewport to preserve readable type | Functionally matched |
| Provider operations | Health table, routing rail, budget, fetch table, raw-payload drawer | Same table anatomy and an interactive replayable drawer with hashes, fingerprint, parser version, IDs, and JSON | Matched |
| Responsive behavior | Clear compact continuation expected | 390×844 has no horizontal document overflow; feed uses two-column metrics and detail stacks in reading order | Matched |
| Interaction state | Selected signal, save/dismiss/brief, provider switches and drawer | Save state, brief creation, outcome link, provider disable, payload inspection, and replay verified | Matched |

## Material mismatches fixed

- Feed action cells originally clipped the final action at desktop width. Column
  geometry and action spacing were adjusted until `Create brief` rendered fully.
- The first mobile row initially serialized every metric vertically. It now uses
  a compact two-column measurement layout and two-column action area.
- The generated detail concept accidentally named an out-of-scope source. It was
  corrected before implementation to `Mock discovery provider`.

## Above-the-fold copy diff

Required product copy and navigation labels are preserved. Three functional
labels not visible in the concept are intentionally present because the product
specification requires them: `All signals` (state filter),
`Provider-independent evidence` (demo provenance cue), and
`Scores expose deterministic components` (score transparency).

No marketing claim, provider claim, social platform, billing copy, or decorative
eyebrow was added.

## Slice 10: private-beta loop

The Pulse, Digest, and onboarding concepts were generated before
implementation. The final 1280 px desktop renders were compared directly with
those concepts; mobile was verified at 390×844 with no document overflow.

| Comparison point | Concept evidence | Final render evidence | Result |
|---|---|---|---|
| App-shell continuity | Same quiet sidebar, selected rail, identity, evidence-mode panel | Pulse, Digest, onboarding, and Operations reuse the production shell and token system | Matched |
| Pulse hierarchy | North star, seven-stage funnel, trend, freshness, latest digest, activity | Same order and open-rule layout; live counts replace illustrative concept counts | Matched |
| Digest contract | Top three ranked signals, decision, demand, timing, evidence, angle, delivery rail | Exactly three stored signals with source links and deterministic Act/Watch/Skip guidance | Matched |
| Onboarding structure | Five-step rail, central channel preview, readiness card | Same three-column desktop structure and stacked mobile reading order | Matched |
| Operational clarity | Not shown in product concept; required by Slice 10 | Dedicated readiness, alerts, recovery point, and dead-letter queue screen | Intentional addition |
| Responsive behavior | Desktop concepts only | Pulse, Digest, and onboarding fit 390 px without document-level horizontal overflow | Matched |
| Copy density | Concise audience demand and activity labels | Demand quotes are bounded to 220 characters and activity uses human-readable surface labels | Matched after repair |

The only material variance is data-dependent: the current live/demo evidence
produces two `Skip` and one `Watch` recommendation, while the illustrative
concept showed one of each. The UI does not force an `Act` recommendation when
stored score, fit, or saturation evidence does not support it.
