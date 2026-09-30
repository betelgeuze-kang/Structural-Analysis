# Validation scoring preserves unknown decisions and total-cost limits

`scripts/score_rc_gate_validation.py` scores a fitted immutable gate against the
separate validation object. It rejects training-sample overlap, validation
cases absent from the policy's whole-case exclusions, duplicate samples and
incomplete denominators. Every prediction is fixed from the original feature
vector before measured labels are scored.

The scorer recomputes each label and cost target from the retained three
repetitions and rejects changed values. It reports true/false positives,
true/false negatives, proposed-but-unverified and declined-but-unverified rows
separately. Unknown rows remain in the declared denominator and verification
coverage. Precision and recall explicitly use verified rows only and remain
null when their denominators are zero. They are not promoted into complete
evaluation metrics when unknown rows exist.

Per-row records retain the original sample, case, parent, producing seed
policy, comparison report hashes, fixed decision and measured target. The
validation object's hash and fitted gate hash bind the score. This assumes
the table assembler's authenticated source inputs; scoring does not replace
source-file, seed-exclusion or numerical-report audits.

Timing covers the decision calls only. Setup, input extraction, validation
and reporting are explicitly outside that interval. The result never claims
total runtime benefit, full-path evaluation, independent project evaluation
or policy promotion. A time-margin training target is not a new wall-time
measurement, and counts alone cannot establish net acceleration.

Nine new synthetic contract tests pass (126 other tests deselected). They
cover all six categories, unknown/zero denominators, sample and case leakage,
duplicate rows and changed labels/targets/counts. Ruff and whitespace checks
pass. The previous complete focused run passed 126 tests before this scorer
was added. These are software-contract checks, not real gate validation results.

The new three-group-excluded label campaign remains unstarted while the
2,048-layer result is being written and audited. Real 99-row training and
33-row validation comparisons remain outstanding.
