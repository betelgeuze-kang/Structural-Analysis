# Separate inner-gate training and validation tables

`scripts/rc_gate_validation_rows.py` assembles a selected declared fold from
the complete new three-group-excluded audit and the complete retained original
audit. Callers must authenticate both campaigns and their producing seed-policy
receipts first; this function is an in-memory contract, not a file authenticator.

Before selecting a fold, it requires complete unique task/sample coverage,
exact task and seed indices, the original producing policy hash, expected case
membership, finite consistent prefix features, original three-repeat labels
and report identities. A source sample must keep the same case, parent and
prefix features across both campaigns. Policies may yield different measured
labels for that same source, as observed in the prior diagnostic.

The returned `training` and `validation` objects are separate. The original
five-group protocol supplies 99 training rows from the other three groups and
33 validation rows from the added validation group. Both that group and the
outer group are excluded from training. The train and validation source-sample
sets must be disjoint. Only the training object can be passed to the cost-gate
fitter, so validation values/labels do not enter fitting, normalization or the
training-table hash used in policy identity.

Verified training rows retain their original cost repetitions and measured
targets. Unknown training rows are kept in `unverified_rows` and are not fitted.
Unknown validation rows remain in the validation list and declared denominator,
with null labels/targets and a separate count. They are not converted to false
labels or removed to improve apparent accuracy.

Synthetic boundary tests change validation feature values to 9,999 and alter
their measured time targets while preserving the same-source bindings across
campaigns. The training object and resulting policy hash remain unchanged.
Tests also reject incomplete/duplicate rosters, foreign policy/seed/label-group
identities, changed parents/features, nonfinite inputs, changed labels and
boolean task indices. The focused runtime module passes **126 tests in 6.99 s**;
Ruff and whitespace checks pass. The small fits inside these unit tests are
synthetic contract checks, not new scientific gate fits or runtime evidence.

The new 2,970-comparison campaign has not yet run, so no actual inner validation
table or selected gate is claimed. This contract prepares the next stage while
the 2,048-layer solve remains active. It does not establish a predictive benefit,
independent project validation or full-path acceleration.
