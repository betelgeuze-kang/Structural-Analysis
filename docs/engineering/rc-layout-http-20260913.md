# Layout artifact admission and immutable HTTP delivery — 2026-09-13

Source `b059066da5d647ddb1379082ae0e4acab1b4e5e7` adds explicit layout-graph
admission to `RcSearchArtifactBundle`, retaining the existing authenticated,
read-only snapshot mount and its file/aggregate budgets. Existing candidate-search
and standalone schemas retain their original reader path.

## What is checked

The reader pins the result hash and checks plan/source/policy/training bindings,
complete historical work, exact pool membership and model bytes. It reconstructs
canonical models, fixed contexts, physical identities, quantities and predictions
from the frozen policy without fitting or executing a structural analysis path.
It recomputes common-price estimates, screens, ranking and shortlists, then checks
original comparison/model/result/checkpoint/verification/invocation references.
A verified row requires every original artifact role. Comparison quantities and
model bytes must match the pool; declared winners must be the cheapest eligible
models among those actually evaluated.

Coverage and finite-pool cost audits are recalculated. Arm work and nonnegative
costs are checked, and the enclosing interval cannot be smaller than disjoint
arm/ranking components. The claimed scope remains non-authoritative: result and
checkpoint engineering replay belongs to subsequent review; byte binding and
metadata consistency are not independent physical validation.

The first reader test exposed a serialization detail: the producer appends
`shortlisted_by` strategies in execution order, while canonical JSON sorts mapping
keys. Reconstructing the fixed price-then-learned execution order preserves the
original audit bytes and does not rewrite prior observations.

## Original prices and supplemental artifacts

New layout-search producers save `price-table.json`. Its reconstructed canonical
price-table hash must equal the existing frozen plan's `price_table_hash`; original
quantities and estimates are then recomputed from that table. Unknown or mismatched
prices are not inferred from the selected result.

The earlier retained search predates this file. Its observer script preserves the
exact `FiberFrameMaterialPrices` constructor values. This observation recovered
those original values into a separate supplemental price document and verified
its hash against the original plan. Every pre-existing search artifact remains
byte-for-byte unchanged. The exported snapshot includes this validated supplement.
Older directories without their original price table are not silently admitted.

## Verification

79 tests passed: 17 layout HTTP/graph tests, 46 existing search HTTP tests and 16
workflow contracts. Tests cover actual original bytes through the authenticated
mount, no filesystem access during HTTP handling, no solver/fit calls during
admission, immutable snapshots, and rejection of mismatched or rehashed plans,
prices, model identities, predictions, quantities, screens, winners/accounting,
missing checkpoints, path traversal, false claims and invalid costs. Ruff, focused
mypy and whitespace checks passed. Development CI includes 36 modules. Initial
audit-order and unauthenticated-POST expectation failures were corrected before
the final passing run; authentication still precedes method handling.

A separate actual loopback HTTP observation used the original budget-two search
report `sha256:6804c5f19ae7d6526fbabe28c545457ea23b73c86faeada8845b45bf7e7d2b0f`.
All 85 exported artifact responses matched their registered original bytes.
Admission took 62.644458 ms. Sequential HTTP transfer and server teardown took
56.737398 ms; these are single observations, not repeated performance evidence.
No new structural path, fresh engineering replay, policy fit or browser review ran.

The portable export and receipts are retained in 89 files / 15,338,910 bytes at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-layout-http-3ghx6dtu`.
Adjacent inventory SHA-256:
`fde3d601091ed140daebda7d3b775d22df23cb181fee408c3227094285a40118`.
See the [machine-readable observation](rc-layout-http-20260913.summary.json).

## Remaining integration

Workbench's current TypeScript search schema still admits only the older candidate
search/strategy formats. Its layout decoder, engineering bindings, rendered review
and original-download browser checks remain open. HTTP admission is a prerequisite,
not proof of that UI integration. The broader runtime, joint split, independent
physical, licensing, owner/administrator, hardware and material/3D roadmap gates
remain unchanged.
