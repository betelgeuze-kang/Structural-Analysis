# Full-reference training labels for fixed-history layouts — 2026-09-13

`generate_control_layout_training_labels` connects the scoped layout dataset to
actual reference analysis and a fresh full-path verification for each training
case. It reuses the single-model execution helper extracted from RC design
comparison; physical acceptance tolerances and the public comparison requirement
of 1–16 alternatives are unchanged.

## Inputs and publication

Call the function in `structural_analysis.benchmark.rc_control_layout_labels`
with the existing immutable case tuple, a full source revision, a new output
directory, `FiberFrameHistoryLimits` and `FiberFrameMaterialHistoryLimits`.
Dataset preflight executes before output creation. Validation and holdout models
participate only in descriptor/split checks, never numerical label generation.

Each training case retains its original model, complete request, result,
checkpoint, verification, invocation start/outcome receipts, work counts and
wall/CPU costs. Ordinal artifact directories avoid using caller case IDs as
filesystem paths. Metadata retains those case IDs. Model bytes and physical
identity are checked against the prepared descriptor before accepting targets.

A sample includes the descriptor, response targets, original artifact references,
request reference and a content hash. `training-samples.json` is published only
when every training case has a complete verified path with known execution work.
A verified result that fails caller performance screens remains a useful labelled
infeasible example. Failed or unverified cases remain visible in the report and
block publication of the training matrix, including after partial success.
Interruptions preserve start receipts and an explicit unknown-work failure record.

The total label-generation interval includes dataset preflight, training analyses,
fresh verification and intervening IO, excluding the final report write. Per-phase
costs are nested components, not additional costs to add to that total. The caller's
source revision is provenance metadata, not an attestation of the running binary.

## Verification and limits

Focused tests execute two real L-frame training layouts with the same six-target
reversing history. Both are reanalysed during verification. A guarded API rejects
any attempted evaluation-model execution. Tests also check original artifact
hashes, request retention, inclusion of verified infeasible labels, returned
verification rejection, raised analysis/verification, partial success, interruption
and preflight rejection before output creation. Existing design-comparison,
candidate-search and workflow-contract tests cover the shared helper and CI list.

Across the focused runs, 111 distinct tests passed: 9 new label tests, 55
candidate-search tests, 21 design-comparison tests, 10 dataset tests and 16 workflow
contracts. The first label test initially undercounted nested fresh-analysis API
calls; its expectation was corrected and the complete label module passed. Ruff,
focused mypy and whitespace checks passed.

The independent development CI list includes this module (33 modules total).
Local test success does not establish hosted full-suite success.

These are internal solver-generated labels from controlled fixtures. No external
measured response is admitted, no new prediction policy is fitted, and there is no
independent physical validation or demonstrated net AI benefit. The dataset remains
fixed-history geometry separation; it does not satisfy the broader joint
project/geometry/load-history generalization requirement. Next work must bind a
new layout policy to these verified samples and evaluate unseen layouts with full
reference costs while retaining the broader roadmap's independent evidence gates.
