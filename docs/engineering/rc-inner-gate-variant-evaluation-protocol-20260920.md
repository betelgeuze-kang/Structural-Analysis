# Fixed inner validation of prefix and material cost gates

`scripts/evaluate_rc_inner_gate_variants.py` compares the two already declared
cost-margin representations on all 20 additional inner folds. There is no new
threshold, regularization or model-family search: both retain ridge 1 and the
0.01 decision threshold. This tests out-of-training behavior of the existing
representations; it does not assume either becomes useful.

Require complete audited new labels with an explicit final inventory hash,
the pinned original labels, both pinned seed preparations and the pinned
accepted-material summary packet. Validate all fold assemblies before any
output directory or fit. Each fold has the declared 99 training and 33
validation source rows; unknown training rows are retained but excluded from
fitting, while unknown validation rows remain in the denominator. If a fold
has no verified training rows, report it without fitting or inventing a score.

Evaluate the prefix-only and material-extended tables with identical original
cost labels. Material values join by source sample, case and parent identity.
Training and validation material inputs remain separate. In particular, the
full material artifact hash, which includes validation and outer-group inputs,
is not inserted into the object passed to the fitter. Artifact provenance
remains in the enclosing experiment plan.

The driver saves each training table, validation table, strict policy, score
and fit receipt separately. There are at most 40 gate fits and zero new solver
calls. The result records actual completed fits, incomplete folds and enclosing
cost. It preserves six score categories and labels inference-call cost as a
partial interval. Historical seed/label costs remain in their source packets.
No winner is selected or policy promoted automatically. These overlapping
development folds are not independent project validation or a full own-history
runtime comparison. Reserved evaluation cases remain untouched.

Local verification: **140 runtime diagnostic tests pass in 7.35 s**. Tests
include unchanged training policy identity after validation-material changes,
foreign material-parent/case rejection, source-table separation and refusal of
unfinished campaign inputs before fitting. Ruff and whitespace checks pass.
These are contract tests; the actual new label campaign has not yet completed,
and this driver has not produced real validation results.

After the shared material-index refactor, a read-only replay at source
`b932ea92ed013f7584e98db4f941949c1d105b8a` reconstructs all five original
material-cost training tables exactly and validates all five original strict
policy identities. No fit or solve is repeated. The receipt is preserved at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-material-table-refactor-audit-deboyth9`,
inventory `267fc7edbf3eef0b94ddd33af53a490ab52d309ec8dff8a8db82c39c3b462c5e`.
Observed replay time before output is 0.264723 s. The original 2-positive /
25-false-positive result remains unchanged and unpromoted.
