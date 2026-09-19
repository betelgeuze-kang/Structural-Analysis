# Replay identity and internally consistent derived diagnostics

The replay comparison now recognizes the exact comparison-metric field set.
Before comparing a metric it recomputes absolute and relative error separately
from each side's primitive product/reference values, using the existing formula
and consistency tolerances (1e-14 relative, 1e-30 absolute). Nonfinite, boolean
and inconsistent diagnostic values are rejected. After that check, the derived
relative-error values are not compared across environments. All other fields,
including primitive product/reference values, absolute errors, tolerances,
quantity identity and contract-pass flags, retain the existing replay predicate.
Numeric acceptance constants and receipt schema/provenance checks are unchanged.
This deliberately changes replay identity semantics; it is not a new physical
acceptance tolerance or a promotion of the saved receipt.

Two tests copied from the saved main-source observation first failed under the
old implementation. After the fix, 13 targeted replay tests pass, including
corrupted diagnostics and small drift that changes contract-pass. The saved main
receipt/replayed comparison pair also passes this revised predicate without
rerunning or editing the original evidence. This does not validate the complete
receipt against the changed source inventory.

A wider selection produced 19 passes and one `receipt_sources_stale` failure
in the CLI current-reference receipt test (four expensive stored-source/replay
checks deselected). Original fixture receipts have not been regenerated or
rehashed to conceal their source mismatch. Ruff and diff checks pass. A separate
full-file run started before the final NumPy-scalar compatibility correction
remains in progress at this record; its result is not claimed as final-code proof.
Hosted development contracts still run at earlier commit 467d2a056 and likewise
do not qualify this change. Full current-source validation remains outstanding.

The source/diagnostic basis is
`main-product-replay-relative-error-diagnosis-20260920.md`. A hosted run must
still establish whether this resolves its failure, and the development branch's
independent external response mismatch is not repaired by this change.

## Final-source regeneration and validation

At committed implementation `bf78fcd15`, a separate process regenerated a product
replay from the preserved same-operator main external receipt. Refresh (including
its internal validation) took 154.463367732 s; an additional current-source
validation with fresh product calculations took 77.320200345 s and succeeded.
The original external bytes were verified unchanged. This is current-product
replay, not new external execution: `external_execution_reused=true`, external
source remains main 234c3122 and its September 14 execution timestamp is preserved.

Crucially, `technical_contract_pass=false` and `current_product_replay_pass=false`
remain. Both bounded planar member-feature and prescribed-settlement comparisons
still fail. The fix allows an internally consistent blocked receipt to validate;
it does not turn those numerical failures into technical passes. No protected
repository receipt was replaced. New hosted or main validation remains necessary.

The earlier obsolete-code full-file run terminated at 18 passes / six failures
in 320.80 s: three stored-source mismatches, two replay mismatches and the old
NumPy scalar rejection. Its loaded implementation predates the final correction;
it is retained as an unsuccessful intermediate run, not final-code evidence.
The final-code focused results above and the separate regeneration/validation
are the applicable evidence. Final full-file stored-receipt acceptance is open.

Packet:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-current-replay-fix-c7xygcg2`.
Input, refreshed receipt, result, execution script and implementation snapshot
are inventoried; all listed hashes were re-read. External inventory SHA-256:
`cf7ced34503825416eb1bcdec8e4256e58f1071a605094f566a6e193ef04c46c`.

## Hosted mismatch localization

A subsequent diagnostic-only change keeps the same replay predicate and appends
the first rejected field path to `receipt_product_comparisons_stale`. It reports
structural/list differences and Boolean contract changes, while consistently
computed relative diagnostics that the predicate accepts do not become spurious
witnesses. No response values or full receipt payload are printed. A validator
integration test uses controlled current-comparison output and confirms rejection
with `path=[0, "contract_pass"]`; it is a synthetic contract test, not a solver
execution. Nineteen focused tests pass, including that test and the prior replay
integrity cases; Ruff and diff checks pass. This provides actionable hosted
failure evidence without changing receipt acceptance or asserting that current
numerical failures are resolved.

Live source inspection also confirms that main still uses direct chord-length
subtraction while the development branch retains the small-motion cancellation
repair in `corotational_frame2d_basic.py`. The prior controlled external arithmetic
diagnosis (`opensees-corot2d-arithmetic-20260910.md`) already investigates the two
remaining reference mismatches. No numerical rollback or reference substitution
was made to force comparison success. The earlier main reproduction and the
current-branch physical-comparison failures remain distinct.

## Independent development coverage

The 17 pure replay-identity regressions now live in
`tests/test_external_product_replay_identity.py`, selected by the independent
development-contract job. They do not read external receipt artifacts or run
solver replays. The original receipt-validation integration test and full-suite
requirements remain in place; tests were moved, not discarded. The workflow
contract enforces the additional file (49 selected files). Pure replay plus
workflow tests: 35 passed; the existing bounded-drift and validator mismatch-path
integration selection separately passed two tests. Ruff and diff checks passed.
This allows future CI to exercise the fix even when external preparation blocks
full shards. The still-running hosted job at 467d2a056 predates these changes.
