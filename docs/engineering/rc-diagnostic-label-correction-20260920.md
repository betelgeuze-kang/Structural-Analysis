# Correct diagnostic names and completed extended-search labels

The original grouped abstention report had a reporting bug. Its numerical range
checks indexed the full 509-value vector but named them using only the appended
408 material-field names. It omitted 83 static model inputs plus 18 causal inputs.
The resulting 101-position shift misnamed some values and eventually caused an
`IndexError` when the larger coverage study reached high-index violations.

The original model inference, range decisions, solver acceptance, training values,
full-path comparisons, timing scores and stored field values did **not** use this
incorrect name lookup. They remain unchanged. The previously stated energy and
steel-plastic field names are withdrawn: all 21 violations in the interior case's
original grouped diagnostic are **concrete compressive-history strains**.
Original erroneous artifacts are retained in their packet and Git history.

`control_policy_feature_names()` now returns the complete static/causal/material
layout. The previously correct training-fold diagnostic supplies the common
naming logic, used by the standalone audits and coverage runner. The boundary
regression checks all positions, including the final material index beyond the
length of the material-only list. All 19 training-diagnostic checks pass; Ruff and
diff checks pass. The corrected NumPy runner and independent Python range audit
agree on every one of the 99 original samples, without any new solver call or fit.

## Full-history result with extended line search

The frozen `05e588704cb7bf6d6b919c8541f6b8733593d1ad` label study completed all
nine training histories and their reference/secant/fresh-reference comparisons.
It retained 99 valid labels and completed its initial fit. All 11 declared
models/requests were compared with the earlier failed study: only the line-search
alpha list changed. The iteration limit and acceptance tolerances did not change.
The two reserved solver paths remain unexecuted.

The original process then exited with an error during diagnostic naming. Its
`learning-study.json`, original labels, policy and all path artifacts were already
complete. The corrected audit reconstructs only the missing range summary into a
**separate audit packet**; it does not rerun or rewrite original measurements.
The original enclosing-process wall time was not saved and remains null.

| Held geometry | History cases | Original labels | Within complementary-family feature ranges |
| --- | ---: | ---: | ---: |
| A | 3 amplitudes | 33 | 0 |
| B | 3 amplitudes | 33 | 33 |
| C | 3 amplitudes | 33 | 0 |

All three amplitude-one feature vectors across their 33 original samples exactly
match the previous baseline campaign. Range eligibility changed from 0/33 in the
baseline to 33/99 after including additional training histories; for B specifically,
its unchanged amplitude-one inputs changed from 0/11 to 11/11 in-range. Each check
excludes the entire geometry family and uses 66 complementary samples. Extreme
geometries A/C remain outside the available geometry envelope.

**In-range reference-parent inputs are not actual runtime proposals, accurate
predictions or acceleration.** The next stage must execute the fixed policies
through the original full-path comparison. No evaluation output is used to select
it, and no learned policy is promoted by this diagnostic.

Known label-generation work is 351 core calls and 1,894 Newton iterations/linear
solves; the stored label-study wall time, including its initial fit, is 134.743 s.
Earlier failed studies and the 12-call single-step probe remain separate costs.

## Evidence identities

Measurement packet:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-history-coverage-extended-a784lw9c`.
All 466 frozen source files match their manifest and exact Git blobs.
Inventory: 2,682 files / 140,787,466 bytes excluding `__pycache__`, SHA-256
`f850f7e65670bf4d6254039da2aca35269cbd1840b645d82308c2402017849f0`.

Corrected audit packet, generated using diagnostic commit `12d5605e9`:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-corrected-diagnostics-k3b_emw6`.
Inventory: 7 files / 70,567 bytes, SHA-256
`e514e18df738d09b789c0f44c8719aefcf31e280f9fbd0b30a9f38028211fa26`.

[Corrected original abstention labels](rc-grouped-runtime-abstention-20260920.summary.json)
and [recovered coverage summary](rc-training-history-coverage-extended-20260920.summary.json)
retain the distinction between numerical source revision and later diagnostic code.

## Next runtime comparison, declared before execution

`run_expanded_rc_runtime_campaign.py` reads the pinned complete-label inventory,
verifies each required input, regenerates and exactly compares all 11 cases, and
uses the existing connected-family runtime selector. It runs nine training cases
× two ridge values (10,000 and 1,000,000) × three counterbalanced repetitions:
54 folds / 216 full paths, with a conservative budget of 4,104 core calls and
19 fits including a possible selected full-training refit. Whole geometry/history
families are excluded; no labels are regenerated and no reserved case is executed.

The selector requires actual learned proposals, all existing full comparisons,
and at least 1% improvement before selecting a learned policy. Existing label
costs remain separate, and passing this internal tuning comparison would not by
itself prove net savings or independent evaluation. The driver records input
verification/preparation and selection time; imports and later audit time are
outside that clock. No prediction is made here about the result.
