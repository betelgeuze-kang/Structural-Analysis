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

## 2026-09-29 exact-main port

The comparison and first-mismatch-path code and tests above were ported onto
main `234c3122c78dea064411aa16b06b18ab16157576` with their original
development-branch code and test patches unchanged. Their patch IDs match
development commits `bf78fcd15` and `007297f9f`; the latter's historical report
sections were not copied into this main-based branch.

The preserved Nightly overlay from run `35536882664` contains 12 comparison
cases. Its comparison rows equal the tracked main receipt. Local replays against
that overlay matched on Python 3.10.12 and on isolated Python 3.12.11 with the
27 packages from the repository's locked CI requirements, including NumPy 2.2.6
and SciPy 1.15.3. These runs do not reproduce the Product State Current failure
from run `35542528427`; that old hosted log reports only
`receipt_product_comparisons_stale`, without a rejected field path.

On the ported source, 18 focused near-zero, integrity and mismatch-path cases
passed, three existing bounded-drift and tampering cases passed, and four other
low-cost metadata, legal-boundary and fail-closed cases passed. A combined
low-cost selection returned 25 passed and five deselected, not a full-file pass.
The existing CLI
check against the tracked pre-port receipt was also attempted and failed with
`receipt_sources_stale`. Direct current-source validation of the preserved
Nightly receipt gave the same expected result: changing the validator changes
its source inventory, while the original receipt remains immutable. The two
long-running refresh tests, stored-receipt current-source test and CLI refresh
test were not rerun on this port.

No stored receipt was rewritten, rehashed or promoted. A new exact-source
hosted execution is still required to see whether the comparison change resolves
the consumer failure; independent verification, legal approval and release
authority remain separate blockers.
