# One fixed prefix-cost tree after the negative linear-gate evaluation

This is a **post-hoc development model-family comparison**, motivated by the [audited linear-gate result](rc-inner-gate-evaluation-results-20260920.md) and the finding that 29 of 32 beneficial validation decisions lie within training feature bounds. Those results have already been inspected; reusing the folds must not be described as untouched validation. Both reserved cases remain untouched.

## Fixed experiment

- Reuse the same authenticated 990-pair triple-excluded training labels and original 660-pair validation labels, with all twenty directed outer/validation folds. Each gate receives only its 99 training rows; validation remains a separate 33-row object.
- Use only the existing prefix features. No new physical features, material summaries, target labels, structural solves or label timing campaign.
- One regression-tree setting: maximum depth **3**, minimum child/leaf support **8**, leaf prediction equal to mean measured worst-repeat margin, proposal threshold **0.01**.
- At each node, choose the feature/cut producing the smallest strictly improved training squared error among admissible splits. Candidate cuts are observed left-side training values with `<=` routing; feature order and sorted values determine stable tie order. A single training-only target scale bounds squared arithmetic. Constant targets remain leaves.
- Preserve the existing positive-training and per-feature min/max guards. Train no more than twenty gates; do not search depth, leaf support or threshold on the evaluated folds.
- Reuse the validation scorer's full denominator, unknown-label handling and original measured label/target/report identity checks. Record every fold, actual fit count and costs separately. No automatic winner, policy promotion, runtime adapter or full-path speed claim.

The tree gives a small piecewise model of the measured cost target; it is not a physical damage model or a probability/confidence estimate. Its inference and any eventual online feature extraction would need charging in a separate complete-path evaluation if development evidence warrants that next step. Historical label-generation costs remain part of the overall learning cost.

## Implementation and checks

`scripts/rc_offline_cost_tree.py` implements strict bounded immutable tree policies and training. `scripts/evaluate_rc_inner_cost_tree.py` authenticates/prepares all folds before writing outputs or fitting. The common scorer explicitly accepts this offline class alongside the existing ridge policies. There is no runtime guard adapter.

Focused tree and existing runtime-diagnostic suite: **155 passed in 7.09 seconds**. The first test attempt exposed duplicate Python module identities in the test harness; using the same script import convention as the CLI resolved it. Ruff and diff checks pass. The CI selection contract passed after registering the new test file (69 selected development modules). These software checks are not real-data evaluation or evidence of model benefit.

Real-data execution has not started at this protocol commit. Freeze this implementation before the twenty-fit run, preserve any failed attempt, and separately audit tree partition support, leaf means, original rows/exclusions and validation decisions without another fit. Do not alter the completed linear experiment or its source packet.
