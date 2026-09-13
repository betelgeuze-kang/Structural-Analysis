# Workbench repeated strategy cohort review — 2026-09-13

Source: `6009579230ac8cdb73b022a2e0feb782324d43b5`. This adds cohort review to the existing
standalone candidate-search interface. It does not create training labels or run
new nonlinear analyses, and does not establish independent physical validation
or a learned net benefit.

## Behavior

Configure `rcControlStrategyCohortUrl` in `window.__STRUCTURAL_WORKBENCH_CONFIG__`
with a same-origin URL ending in `cohort.json`. The existing authorization provider
is used for every original read. All paired original studies and runtime records
are validated before the cohort becomes visible. The browser independently
reconstructs the producer's cost arithmetic, deduplicates historical training by
report identity, retains incomparable pairs and leaves their aggregate ratio null.
Recorded interval sums explicitly exclude startup/imports, runtime-sidecar writing,
transport, Workbench review and separate audits; they are not campaign elapsed time.

Each execution opens the existing full design/quantity/price/result review pinned
to the cohort's report hash. A changed physical artifact, or even a separately valid
replacement report with a different hash, invalidates the complete cohort view.
Original cohort and runtime downloads preserve verified bytes. Worker cleanup uses
the existing abort/disposal mechanism. Validation has bounded metadata and total
byte budgets; original study contents are not posted wholesale into React state.

## Verification

- 58 local contract tests passed, including controlled cohort metadata and existing
  standalone/two-arm regressions. These fixtures are not new physical experiments.
- 14 local browser tests passed: 11 existing search tests and 3 cohort tests,
  covering 1440/390 widths, authorized reads, exact downloads, modified checkpoints
  and a valid replacement report rejected by its pinned identity.
- TypeScript, Vite build, production viewer-delivery and diff whitespace checks passed.
- The original portable packet inventory was checked against
  `390442ef9599a5bcbe29d727ae0ec1dbb2b9633130968405c94c63d1f357c740`.
  The browser validator read 577 inventory-matched originals in
  725.266 ms, retaining 4 pairs / 8 executions / 2 incomparable pairs.
- A separate original-data browser observation opened both desktop and mobile views,
  reviewed selected candidate `w047`, made 4 exact downloads and encountered no page
  errors. It performed 1,238 inventory-matched reads, including download comparisons,
  in 7156.835 ms. This used Playwright route interception, not the HTTP
  backend. Mobile rendering was visually inspected; tables retain horizontal scrolling.

The original cost totals remain price CLI 24.495854346 s, learned CLI 24.592134089 s,
historical training counted once 2.761753795 s. The full cohort's combined ratio is
unavailable because two pairs have incomparable selections. Review timing above is
a separate observation, not a solver acceleration measurement or a reconstructed
end-to-end campaign time. No fit or solve was performed by these observations.

## Reproducible records and remaining scope

Packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-cohort-workbench-lblxt691`. Its sibling inventory has SHA-256
`4c86d131ffc56c48eac793c82387efad68f6669aa61b098380076cc2dba801a3` and binds 14 files / 1,332,258,443 bytes,
including source archive, production asset hashes, validator/browser drivers,
receipts, screenshots and test/build logs. Source inputs remain in their original
sealed packet; none were modified. The large source archive is an observation
storage cost, excluded from the recorded browser interval.

Current-source full hosted CI and end-to-end actual-HTTP cohort browser verification
are not established here. Parent startup, transport/review and audit intervals still
need an explicitly scoped campaign cost comparison. Independent geometry/history
cases, external physical/model qualification, licensing, owner/administrator and
hardware dependencies remain open. Existing evidence gates are unchanged.
