# Verified fixed-history layout response policy — 2026-09-13

Source `75d720f3e9096d1be7921dc4f3c4432974abfb9d` connects fresh training-layout labels to a separate SVD response
policy. `train_control_layout_policy` generates the labels, checks their original
bytes and fits once. This is a candidate-response predictor, not a new displacement
warm-start or an alternative equilibrium solver.

## Contract

The new schema is `experimental-rc-control-layout-policy.v1`. It uses all 163
explicit layout/section descriptors and the existing seven response targets.
The old fixed-family candidate policy cannot decode this schema. The common strict
JSON, finite-array, identity, content-hash and prediction checks are reused without
changing the old policy's schema, dimensions or training-count bound.

The new trainer accepts the existing fixed-history layout roster contract, typed
screen limits and a positive finite ridge. It generates reference labels and fresh
verification, then checks the saved dataset/report/sample/model/request/result/
checkpoint/verification/invocation bytes before fitting. Failed, partial or unknown
work cannot reach fitting. The API generates new labels; this is not a general
importer for arbitrary external study files. Content hashes establish consistency,
not external authorship or executable provenance.

The fit uses centered SVD ridge with an unpenalized intercept. All preprocessing
and target scales derive from training rows. Validation and holdout cases supply
no response labels to this fit. Changing only the holdout geometry leaves fitted
weights and preprocessing unchanged in the focused real-execution test.

Prediction abstains for a training model, different fixed control/material/topology
context, features outside the training min/max, or inconsistent predicted targets.
Within-range status is explicitly uncalibrated. An in-range combination is not proof
of a previously learned physical regime. The learned output has no accepted-result
authority and does not establish joint geometry/history generalization.

Plan, fit start/outcome, policy and training report are retained. Interruption or
failure leaves an outcome without a completed policy. The enclosing training cost
includes preparation, reference labels, fresh verification, original-byte checking,
fitting and intermediate IO, excluding the final report write. Label and fit times
are nested components of that total and must not be added to it again.

## Focused verification

93 tests passed: 22 layout-learning tests, 55 existing candidate-search tests and
16 workflow-contract tests. The real test fixture executes two training analyses
and two fresh verification analyses, then performs an actual SVD fit. Additional
checks cover unseen prediction, seen/OOD/history abstention, immutable round trips,
duplicate JSON keys, Boolean/nonfinite controls, malformed weights/schema/hash,
changed original artifacts/targets/unknown work, partial labels, path traversal,
fit interruption and train-only parameter invariance. Ruff, focused mypy and
whitespace checks passed. Development CI now selects 34 modules; these local
results do not establish hosted full-suite completion.

## Actual small fixed-history observation

The committed local source executed a separate eight-layout pilot: four training,
two validation and two holdout descriptors, each in a distinct conservative shape
group. Full original requests and the observation driver are retained. This is a
controlled example derived from the public L-frame fixture, not an independently
sourced or preregistered experimental campaign.

The policy was fitted once at ridge 1.0, and all validation/holdout predictions plus
a training-response-mean baseline were saved before validation reanalysis. Only
the two validation cases were then analysed and freshly verified. Both holdout
predictions abstained outside training bounds; neither holdout was numerically
executed. The six training/validation reference rows all passed their fresh
verification: 12 analysis/verification invocations and 72 attempted control steps.

| Validation case | Peak translation error vs training-mean baseline | Peak fiber strain error vs training-mean baseline |
| --- | --- | --- |
| a | Learned 6.2384e-7 m; mean 1.2979e-6 m: improved | Learned 3.8059e-7; mean 2.0973e-7: worse |
| b | Learned 2.0495e-6 m; mean 1.9882e-6 m: worse | Learned 1.1118e-7; mean 8.4558e-7: improved |

These mixed errors do not establish superior candidate ranking or search savings.
All observed steel accumulated plastic strain and concrete damage targets were
zero. There is no demonstrated inelastic generalization in this pilot. The four
training rows have 163 descriptor columns, of which 156 are constant; the centered
feature matrix has numerical rank 3. In-range features do not remove that limited
coverage.

Training including labels, fresh verification, byte checks and fitting took
13.344974152 s, including a 0.002254867 s fit. Four predictions took 0.014332815 s.
Validation analysis, fresh verification and result IO took 6.653958183 s. The sum
of these disjoint intervals is 20.013265150 s; it excludes campaign preparation,
final reporting and inventory audit. It is not a repeated runtime benchmark or a
matched candidate-search comparison.

The retained packet contains 79 files / 10,297,526 bytes at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-layout-learning-m281iyj9`.
Its adjacent inventory SHA-256 is
`507d4a94419714f1073844ab68fd51592f3f214755f93740c095434d4c62b711`.
The [machine-readable summary](rc-layout-learning-20260913.summary.json) records
all per-target errors, costs, policy identity and scope flags. Inventory checks
read existing bytes and perform no additional numerical replay.

## Remaining roadmap work

The scoped layout policy does not close the full project/geometry/load-history
split requirement. Independent measured datasets and suitable physical mechanisms
still require their own admission and verification. Prediction error, strategy
selection and net search cost must be evaluated separately; no AI speedup or
material-cost saving follows from fitting this policy. The next integration is a
frozen layout candidate plan with actual reference evaluation and matched baseline
search costs, followed by the existing verified Workbench delivery path.
