# Training-only pre-solve work gate

Source/worktree revision `46de89e4322e1a5b42bff1e0e6f6f3121ef3c6a4`.
The [full training cost profile](rc-training-work-profile-20260914.md) identified
482 secant steps with at least three primary iterations. Test whether information
available before each step can identify this region, before coupling a gate to
any correction policy.

## Data lineage and frozen experiment

Use 964 samples from four original training cases: indices 1 through 241 on each
secant path. Index zero has no secant proposal and is excluded. Inputs come from
that same arm's recorded pre-solve context; labels come from its authenticated
primary-iteration count. Verify context and step file bytes against the original
inventory, current parent against previous accepted checkpoint, current accepted
coordinates against the previous step's absolute coordinates, and requested
history against previous requested targets. Reference-arm contexts are not used.

Seventeen fixed features are current target, target increment, previous target
increment, seven current augmented coordinates (including the load factor), and
seven preceding coordinate increments. No case identity, current solved answer,
current residual, current work or future history is an inference feature. Current
answers are read only for lineage checks and labels, not feature generation.

Freeze ridge=1, an unpenalized intercept, augmented least-squares SVD fitting and
score cutoff 0.5. The score is a linear regression score, not a calibrated
probability. Leave one original training case out per fold: 723 fitting rows and
241 evaluation rows. Standardization is fitted only to that fold's fitting rows.
No hyperparameter or cutoff search is performed. The baseline always predicts
at least three iterations. These are already-inspected, related training cases;
this is NOT an independent project/geometry/load-history held-out campaign.

## Observed predictions

Positive means at least three primary convergence rows.

| Excluded training case | True positive | True negative | False positive | False negative | Accuracy |
| --- | ---: | ---: | ---: | ---: | ---: |
| train-a | 108 | 96 | 11 | 26 | 84.647% |
| train-b | 47 | 88 | 50 | 56 | 56.017% |
| train-c | 106 | 80 | 15 | 40 | 77.178% |
| train-d | 65 | 53 | 89 | 34 | 48.963% |

Combined: 326 true positives, 317 true negatives, 165 false positives and 156
false negatives. Accuracy is 643/964 (66.7%) versus the always-positive baseline's
482/964 (50%). Recall is 326/482 (67.6%). Aggregate improvement hides strong case
variation; train-d accuracy is only 49.0%, versus its always-positive baseline of 41.1%.
The gate would flag 491 steps and leave 473 unflagged, including 156 steps with
at least three iterations. These are classification counts, not avoided solves,
saved iterations or evidence that a correction works on flagged steps.

No numerical solve, tolerance change, gate activation or final policy promotion
occurs. Four research fits produce per-fold coefficients and predictions in the
packet. They are not deployed policy artifacts. Prediction quality alone cannot
prove net savings: it must be combined with an independently effective correction
and evaluated in full paths, including false decisions and fallback costs.

## Cost and audit

Data preparation in the successful run took 70.627935999 seconds. The four fit intervals total 0.003122002 seconds; four 241-row batch transform/prediction intervals total 0.000652142 seconds.

These are separately scoped measurements: batch prediction excludes extracting
features from live solver state and is not per-step production latency. Preparation
excludes imports, the failed preparation attempt, and later audit; complete research
lifecycle cost is not established by summing these fields.

An initial preparation attempt stopped before fitting at train-a index 98 because
it incorrectly required requested target 0.0 to equal accepted coordinate
3.440147142336251e-35. Its script, log and failure receipt are preserved separately.
The corrected check compares requested targets with requested history and accepted
coordinates with accepted history exactly. No numerical tolerance was loosened.

The [receipt](rc-work-gate-training-20260914.json) binds both packets and the prior
cost profile. The audit rereads all bound input bytes, verifies training-only
standardization, recomputes every prediction and confusion count, and verifies
all sealed file lengths/hashes. It performs no additional fits or numerical solves.
Python/NumPy versions, runnable scripts, features, labels and coefficients are
retained. Independent physics, licensing and full roadmap completion remain open.

## Decision

Do not activate this gate. It is a reproducible baseline showing that the work
label is partly predictable but transfers unevenly even within this training
family. Before a more complex classifier, compare its decisions with the measured
benefit of an actual correction on the same parents. Costly steps are not
automatically correctable steps; replacing the adoption target with classification
accuracy would repeat the earlier mismatch between coordinate error and runtime.
