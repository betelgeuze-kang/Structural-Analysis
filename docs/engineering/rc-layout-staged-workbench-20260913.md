# Staged layout Workbench review — 2026-09-13

Workbench now validates staged prefix originals before showing candidate decisions.
A verified cumulative-history violation can reject a candidate early. A prefix pass
or unavailable prefix verification requires a separately verified full path before
selection. Prefix rows never become full-path incumbents.

## Source and implementation

Code and fixture revision: `acdf07e0140f8e7e80df7d06b5b29108e78bd64b`.
The frontend reconstructs frozen request prefixes, model/quantity/price bindings,
original result/checkpoint/verification records, cumulative-limit violations, cost
bounds and prefix-plus-full execution work. It preserves terminal-only limits for
full acceptance. An unavailable prefix verification still binds its request,
result identity and known returned execution work; it cannot establish rejection.

The screen distinguishes prefix rejection, full verified pass/failure, cost skips
and candidates outside the fixed horizon. Seven prefix record roles are downloadable
as original bytes. Downloaded physical records are checked again against their
admitted references; changed bytes invalidate the review and remove selection.
Metadata downloads retain the originally admitted bytes. Existing full-path and
cost-decision downloads remain available.

The fixture contains all 52 original files from the preserved `o0-staged` HTTP
export. Gzip SHA-256: `41188596d30511fa6e49f5cba6abaa2db623a794267ce800d481f004854f2856`.
Its numerical source is `af3793dd3a8a34891ea81c8b76a4428c1a7ae790`; HTTP source is
`55f7f6c270b03c601b4ff5221b22aa481b1ed519`. No labels or numerical originals changed.

## Focused validation and failures

Pinned Node 24.20.0 runner performed TypeScript checking, production Vite build,
viewer delivery verification and selected Playwright tests. An initial TypeScript
nullable-hash diagnostic was corrected before browser execution.

The broad `RC.*layout` selection finished with 86 passes and two failures in 3.1
minutes. Both failures were staged browser download-event timeouts at the eleventh
rapid download, with the review still verified. This pattern is consistent with a
Chromium burst limit; the browser's internal cause was not independently measured.
The test harness was changed to pace clicks by 250 ms and allow 60 seconds for the
18-download scenario. Product code was not changed to hide these failures.

The subsequent `RC staged layout` run passed all 20 tests in 39.5 seconds, including
both viewport download tests, initial/download corruption invalidation, raw-byte
and rehashed semantic tampering, complete work accounting, and unavailable-prefix
verification followed by successful full acceptance. Together the runs cover 89
distinct passing selected tests (69 existing and 20 staged); this is not a claim
that all repository or frontend tests were run. The 69 existing tests include
commercial-layout and viewer-runtime cases selected by the broad expression.
`git diff --check` passed.

## Actual HTTP and browser observation

A clean-source observer served the preserved price-order graph through the Python
WSGI transport and production build, without Playwright route interception. It
reviewed widths 1440 and 390, selecting `middle`, rejecting `small` by its verified
prefix limit, and retaining unknown physical feasibility for cost-skipped models.
Each width downloaded 28 originals: four selected full records, three metadata
files, two cost-skipped pool models, fourteen prefix records and five cost decisions.

- 128 HTTP responses matched original SHA-256 and byte length.
- 56 browser downloads matched original bytes.
- No page exceptions, new numerical paths or policy fits were recorded.
- Both outer panels fit their viewport; screenshots were visually inspected.
- Summed navigation/review/download wall time: 24.494703065 seconds, including the
  explicit 250 ms click spacing. Server startup, browser launch, screenshots and
  teardown are excluded. This is an observation of this review flow, not a speedup.

Sealed packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-layout-staged-workbench-omHQ7P`.
Seven files, 360447 bytes; inventory SHA-256:
`33939e2152cb0af2d02c70aa489c3b29f9ca110a2469d7cba4743d998b264b5f`.
The accompanying summary retains each download hash, original source revisions,
viewport, elapsed scope and explicit qualification flags.

## Remaining boundaries

This is one known-pool synthetic-price, price-order graph. It does not establish
independent physical accuracy, functional equivalence of changed layouts, learned
net benefit, exhaustive minimum cost or release readiness. The earlier two-order
staged/process cost observation excludes this separate HTTP/UI cost; do not add
unmatched intervals or advertise its 6.33% observation as end-to-end AI savings.

Hosted acceptance remains open. At the preceding published head `8daf3e5a908017d4119fe512df48468b33652cd6`,
Repository Python Tests was still running when queried, while Workflow Contract CI,
Native Frame Alpha Clean Install and CI had failures. The workflow-contract job
failed its workflow/provenance/action-pin/CI-streak check. Their root causes were
not resolved by this frontend slice. Current-head full acceptance is not claimed.

Related: [staged HTTP admission](rc-layout-staged-http-20260913.md),
[matched process costs](rc-layout-staged-costs-20260913.md),
[evidence index](rc-learning-search-evidence-index.md).
