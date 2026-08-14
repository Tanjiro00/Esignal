# Design QA — Signals master-detail redesign

## Comparison target

- Source visual truth:
  `docs/design-concepts/signals-redesign-option-2.png`
- Normalized source:
  `docs/redesign-qa/source-normalized-1440x1024.png`
- Browser-rendered implementation:
  `docs/redesign-qa/final-1440x1024.png`
- Full-view comparison:
  `docs/redesign-qa/comparison-source-vs-implementation.png`
- Focused decision-panel comparison:
  `docs/redesign-qa/comparison-focused-panel.png`
- Route and state: `/signals`, default filters, first signal selected.
- CSS viewport: 1440 × 1024.
- Source pixels: 1487 × 1058.
- Implementation pixels: 1440 × 1024.
- Density normalization: source resized to 1440 × 1024; implementation
  captured at the same CSS and pixel dimensions with the in-app browser
  viewport override.

## Findings

No actionable P0, P1, or P2 differences remain.

- Fonts and typography: passed. The implementation retains the selected
  serif/sans hierarchy, readable body sizes, label hierarchy, wrapping, and
  restrained weights.
- Spacing and layout rhythm: passed. Sidebar, search/filter row, 38/62
  master-detail split, row dividers, metric grid, and persistent bottom actions
  follow the selected composition without clipping.
- Colors and visual tokens: passed. Existing EarlySignal ink, canvas, line, and
  lime tokens map directly to the selected design. No gradients or unintended
  elevation were added.
- Image quality and asset fidelity: passed. The screen has no primary raster
  imagery. Existing project icons are used consistently. The mock's decorative
  channel-avatar strip is intentionally represented by real evidence counts
  because the feed contract does not expose channel artwork; no placeholder
  avatars were introduced.
- Copy and content: passed. The screen has a single product goal, explicit
  labels, plain-language evidence, one primary `Build brief` action, and
  secondary actions in an overflow menu.
- Responsiveness: passed at 390 × 844, 740 × 755, 1024 × 900, and
  1440 × 1024. There is no horizontal overflow. Mobile rows expose metric
  labels and `Review details`; the selected section lands below the fixed
  header.
- Accessibility: visible focus styles remain, selects and actions have
  accessible names, mobile labels do not depend on column position, and
  practical touch targets are retained.

## Comparison history

### Iteration 1

Evidence: `docs/redesign-qa/initial-1440x1024.png`.

- [P1] Primary `Build brief` CTA rendered white instead of lime.
- [P2] Publishing-window value wrapped awkwardly.
- [P2] Generic why-now copy was less decisive than the source.

Fixes:

- Forced the selected lime token on the primary CTA.
- Added compact metric typography for long values.
- Replaced generic first-signal evidence with specific safety, tooling, and
  creator-coverage statements.

### Iteration 2

Evidence: `docs/redesign-qa/fixed-1440x1024.png`.

- [P2] Metric explanations present in the source were missing, leaving the
  values less understandable.
- [P2] Mobile selection scrolled under the fixed header.

Fixes:

- Added concise explanations under all four decision metrics.
- Added responsive scroll margin to the selected-signal section.
- Added explicit mobile metric labels and a visible `Review details` affordance.

### Final pass

Evidence:

- `docs/redesign-qa/final-1440x1024.png`
- `docs/redesign-qa/final-390x844.png`
- `docs/redesign-qa/final-mobile-selected-390x844.png`
- `docs/redesign-qa/detail-740x755.png`

The full-view and focused comparison show the selected composition, hierarchy,
tokens, CTA, and responsive behavior represented faithfully. The remaining
differences are P3-level product-data adaptations: evidence counts replace
decorative avatars, and the momentum line renders the deterministic demo
series rather than copying the mock curve.

## Functional verification

- Search, lifecycle, and date-range controls are implemented.
- Lifecycle filtering was tested in the browser: `Emerging` produced one row,
  and reset restored the top four.
- Selecting a signal updates the decision canvas and scrolls correctly on
  mobile.
- `Open evidence`, save/dismiss overflow actions, and `Build brief` use the
  existing API-backed workflow.
- End-to-end signal → evidence → save → brief → outcome flow passed.
- Browser console errors and warnings: none.

## Follow-up polish

- Add real channel artwork only if the provider contract later exposes stable,
  licensed thumbnail or avatar URLs.
- Consider replacing the deterministic straight momentum series with denser
  snapshots when live ingestion is added.

final result: passed
