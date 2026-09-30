# Standalone layout HTTP admission — 2026-09-13

Source `6512d5090943033aa29ab406bcb25ce8608a7e99` admits the explicit standalone
layout result/plan schemas into the existing immutable, authenticated artifact
HTTP snapshot. The original two-arm layout schema retains its existing path.

Standalone admission requires exactly its declared price or learned arm, no
oracle, matching plan/result strategy and the standalone timing scope. Price
order requires null policy/training hashes and historical cost, no predictions,
null ranking and zero recorded ranking time. It does not load or execute a policy.
Learned order retains original policy/training binding and prediction recomputation.
Both paths reconstruct the original models, fixed context, quantities, prices,
shortlist, screens, selected eligible minimum, numerical work and cost/coverage
audits through the shared checks. Physical row artifact hashes, bounded reads,
path validation, pinned result hashes and immutable HTTP bytes remain required.

Admission does not replay numerical paths or provide independent physical
verification. Result/checkpoint engineering review remains a subsequent layer.
Original records and qualification flags are preserved without rewriting them.

## Verification

Ruff and focused mypy passed. The focused Python run passed **103 tests** across
layout HTTP, layout search and existing search HTTP modules. Sixteen new cases
cover both actual standalone strategies, exact HTTP bytes without new solver or
training execution, and rejection of rehashed strategy/oracle/timing/coverage/
training/extra-arm changes and corrupted original checkpoints.

A separate actual loopback WSGI observation loaded all 12 executions from the
previous sealed standalone cost campaign. It checked each admitted artifact
against that packet's inventory and delivered **440 byte-exact HTTP responses**.
No new numerical paths or fits ran. The price snapshots contain 25/33/49 files at
budgets 2/3/5; learned snapshots contain 27/35/51, adding policy and training files.
The previous measurement source was
`596e058f167e8663f62e3bc3e8c6ab0bff18807a`; no original graph bytes changed.

HTTP transfer and server teardown took 0.268066080 s for this single observation.
Admission costs are recorded per execution in the summary. These intervals were
not included in the previous process-cost experiment and are not a speedup claim.
No browser or Workbench review ran in this observation.

The retained export/receipt packet is at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-layout-standalone-http-k2szhu8w`:
443 files, 68,367,877 bytes, inventory SHA-256
`6bfbec705085bc7b964d6acd2ec22266a8443d92bcb425604940b5d13fcbdca9`.
See the [machine-readable record](rc-layout-standalone-http-20260913.summary.json).

## Remaining scope

This closes standalone layout artifact admission and actual HTTP delivery for the
observed graphs. Workbench decoding/display of these standalone schemas remains
open, as do full analysis-to-review cost accounting, AI net benefit, independent
generalization and physical validation, functional equivalence, hosted full CI
and the broader material/3D roadmap. Local tests and original byte delivery do
not imply release qualification.
