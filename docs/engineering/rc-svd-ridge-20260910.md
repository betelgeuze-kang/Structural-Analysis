# Fixed-ridge numerical diagnosis and optional SVD fitting

Source `c4bf0dc4964ef5fba610b4581cf77ea70d5794a9` adds the explicit
`fit_solver="svd-ridge.v1"` learning-study option and v5 policy identity. The
default remains the original normal-equation fit. Legacy, normalized-history
and committed-material feature profiles retain their exact model, arithmetic,
DOF, shape and source-hash validation. A v5 policy additionally binds the SVD
method; case-withheld diagnostics preserve that method in every refit.

The SVD computes the same fixed-ridge objective, including the same penalized
intercept and train-only feature/target scaling, without forming `Z.T @ Z`.
For `Z = U diag(s) V.T`, weights are `V diag(s/(s*s+ridge)) U.T Y_scaled`.
All singular directions receive this ridge filter; no fitted rank cutoff or
hyperparameter search is introduced. The numerical rationale is consistent with
the [official Ridge solver discussion](https://scikit-learn.org/stable/modules/generated/sklearn.linear_model.Ridge.html).
This implementation uses existing NumPy, not a new scikit-learn dependency.

The plan, fitted policy and study report record the chosen method. Missing,
unknown or malformed v5 fields reject; unchanged defaults omit the new field.
Proposals retain the existing range, context and reference-solver acceptance
checks. Selecting SVD does not promote a learned candidate or grant net savings.

## Separate formulations on the original training cases

The [preceding material experiment](rc-material-feature-folds-20260910.md)
has 500 features, including 408 committed native fields, and four authored
training cases with 964 total pairs. Its normal systems have condition estimates
near `1e11`, so numerical error needed separation from case-transfer failure.

The original sample, policy and fold-report bytes match the preceding sealed
inventory before copying. Their hashes, splits, sample order and each fold's
training-only means/scales are checked. Existing validation/holdout responses
are not read. These remain development folds within one authored project, not
independent campaigns.

For each of the four existing folds, the observer fits the same 723 training
pairs with two formulations: direct SVD ridge, and least squares on
`[Z; sqrt(ridge)*I]`, with zero target rows appended. Both retain ridge `1e-6`,
the same intercept penalty, original target scales and 241 withheld pairs.
This adds **eight fits** without structural solves or material integrations.
Both formulations use NumPy 1.26.4 in the same environment; this is an algebraic
cross-check, not independent library or physical-solver validation.

| Withheld training case | Range-eligible pairs | SVD learned/secant RMSE range | Training design-matrix numerical rank |
| --- | ---: | ---: | ---: |
| train-a | 0 / 241 | 33.281-350.012, ungated only | 167 |
| train-b | 241 / 241 | 45.388-216.246 | 165 |
| train-c | 0 / 241 | 766.207-3397.908, ungated only | 166 |
| train-d | 0 / 241 | 27.431-237.603, ungated only | 164 |

Ratios refer to six separate non-controlled augmented coordinates; values above
one are worse. They are not an aggregate across physical quantities. Across these
coordinates, replacing normal equations changes RMSE by at most **0.008011%**.
SVD and augmented least squares differ by at most `4.659e-12` in their predicted
original augmented coordinates. The severe negative result persists.

The design matrices have 501 columns including the intercept. Using the declared
diagnostic threshold `eps * max(Z.shape) * s_max`, their training-row projection
residual maxima are `1.35e-13-2.66e-13`. Withheld-row residual norms against those
same training row spaces are **1.20-4.07** in standardized feature coordinates.
For the sole individually range-eligible case, train-b, they are **1.28-1.41**.
Thus individual feature bounds do not describe the joint feature relationships
observed in these training cases. This is a measured representation difference,
not a new rejection threshold or proof of a single cause of the prediction error.

## Integrated v5 execution

After the tests pass, the committed implementation is retained with 439 source,
schema and selected-test files matching Git. It performs one full-training SVD
fit and four case-withheld fits from the same original rows. All **four stored v5
coefficient arrays and four withheld RMSE arrays match the separate SVD calculation
exactly**. The final audit checks source and original file bytes again.

The two observations together add **13 fits**, no structural calls and no material
integrations. Original numerical label-generation costs remain in the earlier
study; reused labels are not newly free training data. No expensive full-path
run is admitted for this unchanged, unsuccessful candidate.

The algebraic comparison takes 1.350039 s after NumPy import, within a 1.513051 s
parent interval; the eight fits total 0.332985 s. Worker CPU is 1.349572 s and peak
RSS 271196 KiB. The integrated full fit takes 0.106242 s; its four-fold diagnostic
takes 0.912104 s. Worker time after imports is 1.491426 s, CPU 1.491372 s and peak
RSS 341172 KiB, within parent time 3.335099 s. Source/input preparation precedes
those parent intervals. Final source/data audit time is 1.316368 s internally,
CPU 0.220186 s and peak RSS 2479952 KiB. These nested and distinct scopes must not
be counted twice or interpreted as exclusive-host or full-project timing.

The selected tests pass **106 cases in 157.65 s**. An earlier 14-test run in
1.67 s overlaps. Tests cover rank-deficient/near-duplicate inputs against augmented
least squares, refusal to use the normal solver for the SVD profile, strict v5
validation, withheld changes leaving that fold's fitted policy unchanged, and
actual reference/proposal paths for legacy/history/material profiles, including
constant preload and retained arithmetic. Ruff, two-source mypy and diff checks
pass. These are local authored tests, not an external physical acceptance result.

All worker, parent and audit processes are confirmed absent before sealing:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-ridge-numerics-zck8ugir`.
The packet has **459 files / 84834655 bytes**, inventory SHA-256
`51cfc77078aee7dffdc77ed4e7de005427c06769d7fbe7f430b599020e12794a`.
Every file is reread exactly; sealing takes 0.180353 s. The
[machine summary](rc-svd-ridge-20260910.summary.json) retains all coordinate errors,
rank/projection diagnostics, costs, source identities and process checks.

This provides an explicit numerical method and rules out normal-equation rounding
as an explanation sufficient to remove this particular large error. It does not
establish learned runtime benefit. Further training-only model selection needs
joint input support, regularization and independently diverse physical cases;
additional time samples of the same few cases do not create independent projects.
Public experiment/model correspondence, licensing, broader solver verification,
current-main integration and the full roadmap remain open.
