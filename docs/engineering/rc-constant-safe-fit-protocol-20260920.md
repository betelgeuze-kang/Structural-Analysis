# Opt-in exact-constant centering for RC seed fits

The retained seed diagnostic found 48 spurious normalized constant columns in all ten 99-row fits. The new `svd-ridge-exact-constant-centering.v1` method uses policy schema v6. Existing normal-equation and `svd-ridge.v1` behavior, defaults and artifacts remain unchanged.

For each exactly constant training feature (`min == max`), its mean is the identical first-row value and its scale is one. Other means/scales retain the existing calculation; no near-constant epsilon or validation statistic is introduced. Exactly constant target columns use a unit target scale. The SVD ridge solve and penalized intercept are otherwise unchanged. The v6 decoder requires the exact method identity and verifies constant feature means/unit scales after the ordinary schema, dimensions, finite-value and hash checks.

The runtime selector uses this method only when its input policy explicitly names it, and retains that choice in every withheld fit, final candidate refit and plan. Legacy inputs continue to request the existing SVD method. Neither path automatically promotes a candidate.

## Fixed next development comparison

Freeze the implementation before fitting. Reuse the authenticated original 165 labels and ten complementary 99-row seed fits. For each of those ten fixed training sets, perform one v6 fit with the original ridge and OOD margin; compare preprocessing and predictions with its retained v5 policy. No ridge search, near-constant threshold search, reserved-case access or new structural labels. All original validation identities stay separate from training.

Record zero-centered constant columns, unchanged nonconstant transformations, method/policy identities, training-only normalization, fitting cost and both improvement and deterioration in correction error. This is post-hoc development after seeing the old folds. Coordinate error alone cannot select a runtime winner. A subsequent same-parent repeated cost comparison and an actual full-path evaluation remain necessary before claiming benefit; original reference checks and total-cost accounting are retained.

The modification is a numerical preprocessing correction, not proof of physical accuracy, faster nonlinear analysis, independent generalization or release readiness.

## Implementation verification

The combined original SVD/runtime-selection run passed 79 checks in 146.67 seconds. Two additional checks added after that collection passed separately: near-constant values remain distinct, and the runtime selector carries v6 through candidate refits. The final SVD file passes all 12 checks; 81 distinct checks were exercised overall. Ruff and diff checks pass. These include independent augmented least-squares agreement after removing constant columns, legacy reproducibility, rehashed preprocessing rejection and held-out-data isolation. Injected runtime costs exercise selection plumbing and are not speed evidence.
