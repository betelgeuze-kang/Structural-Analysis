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
