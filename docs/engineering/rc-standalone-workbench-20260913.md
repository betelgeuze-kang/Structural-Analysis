# Workbench review of standalone candidate strategies

Source `5c80b7abc7e5a6c6ddb202cdb19733687c320562` adds browser-side validation and
display for the explicit standalone strategy schemas. The same worker/provider
and nested full design validator used by two-arm studies remain in use. Each
standalone report must name exactly one matching plan/arm and no oracle. Price
order requires null learning identities, no predictions or training metadata,
and zero ranking time; the browser never reads its policy/training files.
Learned order retains the existing training identity/disjointness, prediction,
screen and ranking reconstruction checks.

Before rendering, the validator checks original model bytes, member quantities,
common prices, full-path design records, native artifact bindings, selected
candidate, work counts and declared timing scope. It recomputes cost audit
fields. A standalone full-pool run is not silently promoted to a separate
exhaustive oracle: absent oracle minima, gaps and missed-cheaper counts remain
null. This preserves the producer's declared evaluation scope.

The UI displays only the executed strategy and opens its verified design
records by default. Price order has no learning/download controls. Learned
coverage distinguishes an absent strategy from an unrequested candidate.
Original report, plan and available physical artifacts remain downloadable
without changing bytes or executing a solver. Parent-process timing and the
unbound volatile runtime sidecar are not represented as part of this graph.
The displayed report times explicitly exclude final report writing.

## Regression and original-record observations

All **48 contract tests** and **15 browser tests** pass. The browser tests include
four new standalone desktop/mobile cases using controlled metadata conversion
of existing fixture originals. Existing two-arm browser and real HTTP regression
tests also pass. TypeScript, production build, viewer-delivery contract and diff
checks pass. An initial compatibility failure exposed reordered shortlist
membership arrays; the original price/learned array order was restored before
the passing runs. Source physics and original fixture bytes were not changed.

The new validator additionally reads all eight actual standalone numerical
reports from the sealed prior experiment. All **568 original-file reads** match
the pre-existing inventory. The intended single arm, original selected design,
quantities and cost audit pass in each case. Budget-3 price order has no selection;
learned order selects w047. All four budget-11 executions select w047, while
their missing separate-oracle cost minima correctly remain null. This Node
validation observation takes 719.233020 ms and runs no solver or fit.

Two actual budget-3 original reports are then reviewed at 1440 and 390 px in the
built browser application. All four views verify. **172 artifact responses**
and **24 downloads** match original bytes. Price selection is displayed as
None; learned selection is w047, with scoped synthetic estimate 157.5108. The
infeasible price baseline cannot be selected, but its original details and
artifacts remain inspectable. No browser page errors occur. Desktop selected
design and mobile original-detail screenshots were visually inspected.

This original-data browser observation uses route interception to provide
inventory-verified bytes. It does not claim a new real-HTTP backend observation;
that layer was tested separately in the preceding delivery study. The successful
browser observation takes 7.100371940 s, excluding later receipt/seal writing.
Its first harness attempt incorrectly tried clicking the disabled infeasible
baseline selection and timed out. That observer and failure record are retained;
the failed interval was not separately metered. The corrected harness opens
the details disclosure and asserts disabled selection. No product change or
numerical rerun was needed. Browser contexts and the preview server are terminal.

## Scope still open

Single-execution Workbench review is connected. A repeated-cohort adapter must
still bind parent/runtime sidecars, shared historical training and equal-quality
comparisons before presenting complete strategy costs. Broader held-out
project/geometry/history cases, learned net benefit, independent physical
verification, hosted full CI and release approval remain unproved.

The [machine summary](rc-standalone-workbench-20260913.summary.json) retains
source revision, original identities, observations and seal. The packet is
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-standalone-workbench-jAH7gm`:
18 files / 52,700,148 bytes, all reread against the inventory. Inventory SHA-256
is `a10c3620ae6f1a39694d478cdcb6d0cdda0dbc254d3248f5ccc7b587bb24b6fc`.
It includes source archive, built-asset hashes, logs, original validation bundle,
browser receipts, screenshots and the failed observer. Original numerical and
HTTP packets remain unchanged.
