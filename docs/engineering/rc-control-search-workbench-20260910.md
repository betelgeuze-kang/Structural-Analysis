# RC control search: combined Workbench review

The Workbench now consumes the direct-control candidate search, showing both
online strategies, optional later exhaustive evaluation, full-path design
results, quantities, declared prices and candidate coverage in one review.
The final frontend source is `beb540a9cba7a89789efdcd7f9aa239d3359c2dc`.
This supersedes the combined-panel gap in the preceding
[candidate selection observation](rc-control-candidate-selection-20260910.md)
for this locally verified format and authored regression corpus.

## Producer and consumer contract

The CLI's `workbench_search_report` points to `result.json`. Search reports use
`experimental-rc-control-candidate-search.v2`; the plan is now v2 and includes
original canonical model files for every pool member, including alternatives
not requested by either online strategy. Those files are written before any
online structural call. Existing numerical reports and sealed packets are not
rewritten or relabeled.

A host can configure `rcControlSearchUrl` on its existing Workbench runtime
configuration with the same-origin URL of this report. All files beneath the
CLI search output must be served from the same directory hierarchy. The optional
existing `jobAuthorization` callback supplies tenant/bearer credentials. No new
service artifact mount or deployment is created by this UI change.

The worker checks report/plan/policy/historical-training logical hashes,
complete pool and prediction denominators, recorded ranking/shortlist rules,
requested limits and all outcome bindings. It runs the existing design
validator on each strategy and optional oracle, including original accepted
history, fresh verification, model changes, quantities and common-price
estimates. Every pool model has an exact-byte reference; member quantities and
estimates are recounted from its original geometry, including unrequested
alternatives. Whole-pool coverage and recorded prediction errors are recomputed
against the later oracle. Missing evaluation is unavailable, not zero.

Transport checks precede credential acquisition, constrain origin/directory,
reject redirects and bound metadata, individual files and total review bytes.
A shared worker connection retains cancellation, timeouts and fail-closed
handling. The design panel reuses its existing verified-result renderer and
original-byte downloads. A changed subsequent payload retires the worker and
removes the whole search review, including candidate selection.

Historical fitting costs remain separately hash-bound declarations; the browser
does not reload every historical training label, refit the policy, authenticate
an execution identity or certify independent dataset partitions. Recorded
predictions are not physical authority. Producer flags declaring no browser
review are not changed into independent acceptance by opening the UI; the local
browser receipt below is separate evidence.

## Actual regression generation and audit

Frozen numerical source `30bb2d62344836d0f99a6043a07448e9a4db81d1` generates the
training corpus and a search with an exhaustive oracle. A separately reserved
search uses the same already generated policy and no oracle. Both preserve the
previous authored 3 m cantilever widths, seven small reversal targets and -600 kN
constant preload. This reuses a development family; it adds no external or
independent learning samples. Limits and price values remain permissive,
synthetic inputs.

| Actual phase | Core calls including fresh verification | Newton / linear | Internal elapsed seconds |
| --- | ---: | ---: | ---: |
| Training, generated once | 48 | 128 / 128 | 2.715989 |
| Both online strategies and later oracle | 128 | 340 / 340 | 7.277840 |
| Separate search without oracle | 64 | 176 / 176 | 3.615074 |

The generation observation contains **240 core calls, 644 Newton/linear counts
and 30 complete paths**, including fresh replays and preload. The historical
training declaration appears in each search export but its actual generation is
counted once above. Parent startup/CPU/resource records remain in the machine
summary; these shared-host regression timings are not performance evidence.
Tests and review work are separate from the numerical generation counts.

The original-record audit checks 514 frozen source files, six full comparison
reports and all 15 original model-result rows, plus policy/plan/coverage bindings.
It verifies every committed fixture file against the actual generated original.
The audit takes 0.032751 s with no new fit or structural solve. Every online
strategy and the later oracle selects `cheap`. Both strategies leave `middle`
and `costly` unrequested; those alternatives pass the later oracle but are more
expensive. The no-oracle report correctly has unavailable whole-pool counts.
Neither observation demonstrates a learned advantage.

## Frontend verification and corrections

The existing official `verify-workbench-v2-e2e.mjs` includes the two new search
specifications. It runs with the repository-pinned Node **v24.20.0**, executable
SHA-256 `89af8424dd53e560b1933f87ba650d8bf57c83ca5a04600eefb31f416aabbae7`.
Type checking, production build and the existing viewer-delivery contract pass.
The test host intercepts same-origin artifact requests using Playwright and
synthetic credentials; this is not a real tenant/service mount qualification.

The initial run has 17 failures / 40 passes. Fourteen browser failures expose
a real worker-bundling regression introduced by the shared connection helper.
Worker factories now retain Vite's static `new Worker(new URL(...))` pattern
at the provider call sites, while creation still occurs after authorization.
Three tests had incorrectly expected insignificant outer metadata whitespace
to violate a logical document hash; they now mutate metadata content while
payload tests continue to require exact bytes.

The second run has 4 failures / 53 passes: those three metadata test assumptions
and one test that inspected the old verified UI state before an asynchronous
failed download had completed. The test now waits for the required invalid
state. Neither artifact validation nor the fail-closed behavior is relaxed.
The full selected frontend run then passes **57 tests**, including existing
RC design regressions, both search modes, mutations, credential guards, exact
original downloads and worker retirement.

Visual inspection then identifies excessive mobile table wrapping. Search tables
now scroll horizontally with readable column/button widths; displayed strategy
times are rounded to milliseconds while original downloads stay unchanged.
All **four affected desktop/mobile browser tests** pass again, with button
readability and panel bounds checked at 1440 px and 390 px. These four are repeat
checks, not additional distinct cases. Both final screenshots are visually
reviewed. The positive combined-review tests check twelve exact-byte downloads
per viewport across strategy-specific designs and search metadata.

The producer's pool-export checks and existing RC design regressions also pass
**45 selected Python tests** in 17.54 s, with Ruff and scoped mypy passing.
The fixture directories contain 84 and 48 generated original files respectively,
plus their provenance files. Source declarations, hashes, costs and the original
failed-run logs remain preserved.

## Preserved evidence and remaining scope

The packet is sealed at `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-control-search-ui-6hrurhx7`, with **811 files / 20,582,838 bytes** and inventory
SHA-256 `18c9d9750613031c6ca677c5aa27709b22cbfa32bc40e1cdd196565bc3a4d369`.
It contains frozen numerical and final frontend sources, originals, audit,
terminal records, all frontend attempt logs and before/after screenshots.
See the [machine summary](rc-control-search-workbench-20260910.summary.json).

M4/M5 gain a combined local review with verified model/result/quantity/price
bindings. Actual service hosting, repeated independent-family comparisons,
full learned net benefit and external physical validation remain open. This
change does not close those requirements, approve a design or complete the
full Structural Analysis roadmap.
