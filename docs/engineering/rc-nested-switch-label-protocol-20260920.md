# Nested switching-label protocol: prepared, not executed

The next development experiment measures whether a learned seed is useful at a retained native parent. Both the outer group and the group supplying the measured parent are excluded from seed fitting. This prevents the direct outer-group leakage present when reusing the earlier 132-sample policies for nested gate labels.

The ten already fitted policies each use exactly 99 original samples. The generator binds each policy to the pinned seed packet, recomputes the declared complements, and binds every label input to the original sample, native parent, context, model and loading request. No new fits or reserved evaluation are performed by preparation.

## Fixed scope

- 20 directed outer/inner group tasks, 660 policy/parent pairs.
- Three counterbalanced repetitions per pair: 1,980 comparisons and 7,920 planned single-target paths, including fresh reference checks.
- Maximum 11,880 core calls, with actual work retained per report and independently audited.
- Positive label only when all three comparisons pass, all three decisions actually propose a seed, and each proposal-arm time is at most 0.99 times secant. Failed comparisons remain unverified, never negative or positive training examples.
- Proposal-arm time includes material capture, inference, numerical execution, recovery and arm I/O. It excludes prior label generation, prior fitting, later gate fitting and independent audit; these scopes remain separate. Earlier seed fit time is contained in the recorded seed-stage time, not added twice. Later historical normalization/inventory costs were not fully timed.
- Bounded policy parsing reuse starts in a fresh process; exact ordered LRU accounting is audited. Cache state is not reset per arm.

Guard inputs are static model features, requested displacement, displacement increments and the two most recent accepted coordinate states. Material snapshots, step count, case identity, measured execution time and outcomes are excluded from the feature vector. Feature values are recomputed from the retained originals during auditing.

## Verification and limits

Preparation verified all 660 pairs, with zero new solves, fits or reserved evaluations. Focused tests cover material/prefix-length invariance, complete-repetition requirements, abstention, failures and invalid measured times. Existing registered runtime-cost tests also retain guard behavior and timing coverage. The focused file passes 48 tests in 5.63 s; the combined runtime-cost, learning, runtime-selection and iteration-cost suite passes 178 tests in 268.16 s. Ruff and whitespace checks pass.

The numerical campaign has not run and no switching classifier has been fitted. The 1% threshold is a fixed development label rule, not a statistical confidence claim. Ridge 10,000 was chosen from prior development evidence, so nested group exclusion does not establish independent hyperparameter selection. Same-parent local labels do not demonstrate faster complete nonlinear paths: a future trained gate must be evaluated on its own accepted histories with all applicable costs. Reserved evaluation remains untouched.

Related retained evidence: [seed preparation](rc-nested-switch-preparation-20260920.md), [pre-capture guard](rc-pre-capture-guard-20260920.md). All roadmap goals and independent verification requirements remain open.
