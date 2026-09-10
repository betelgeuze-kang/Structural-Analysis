# Candidate learning at a fixed synthetic feasibility boundary

Source `bdc945efc4f74f2a7f45c81a87e2d2365d52f4cf` fixes two biases in the direct-control candidate learner:
exactly constant feature columns now normalize to zero, and SVD ridge penalizes
slopes while leaving the affine intercept unpenalized. The old fitting method is
still explicitly selectable with `--fit-method svd-ridge-penalized-intercept.v1`;
new training defaults to `svd-ridge-unpenalized-intercept.v2`. The training plan
and report identify the method. Serialized v1 policies retain their existing
affine representation, interpretation and hashes. Candidate predictions still
only order actual reference-verified analyses.

The result is a bounded feasibility-search observation: the centered policy finds
a feasible candidate at budgets where price order and the legacy policy do not.
It nevertheless misses the cheapest feasible candidate. This is not evidence of
net runtime savings, independent generalization or real construction savings.

## Diagnosis and fixed protocol

The original three training models have widths 0.32, 0.40 and 0.54 m. Their
maximum absolute fiber strains are 0.00035694739249473445,
0.0003396259042878965 and 0.00032092328070523475. The legacy policy predicts
0.0003200497064371905, 0.0003082091198845259 and 0.0002874880934173627 on
those same models. Its mean prediction is 0.9 times the mean label.

Two feature columns contain the identical value 0.05 in every training row, but
floating-point mean/std arithmetic gives a tiny positive scale and normalized
values of -1. Together with the appended intercept, the legacy fit has three
constant basis vectors, all penalized. This explains why its observed mean ratio
is 0.9 rather than the simple one-intercept ratio. The centered fit explicitly
handles exact constants, centers the responses and normalized design, fits only
slopes, and restores the response mean. Its mean strain prediction equals the
mean label in this observation. Mean preservation is not calibration or a proof
of accuracy on new inputs.

Before new pool predictions or solves, the protocol fixes:

- Training widths 0.32 / 0.40 / 0.54 m; evaluation baseline 0.43 m.
- Alternatives 0.34 / 0.36 / 0.38 / 0.42 / 0.46 / 0.48 / 0.50 / 0.52 m.
- A strain limit of **0.0003302745924965656**, the arithmetic midpoint of
  the original 0.40 m and 0.54 m training labels. This is a synthetic experimental
  limit, not a code-based design limit. Other declared limits and prices remain
  the prior synthetic values.
- A 600 kN constant axial preload, followed by seven displacement targets
  -0.002 / -0.004 / -0.002 / 0 / 0.002 / 0.004 / 0 m, with two reversals.
- Ridge 1, OOD margin 0, and budgets 2 and 6, each **including the baseline**.
- Legacy training, centered training, legacy budget 2, centered budget 2,
  legacy budget 6, then centered budget 6 with the sole exhaustive oracle.

Both methods regenerate the same three verified training labels; the two sample
files are exactly equal. All eight online arms finish before the oracle runs.
Both rankings are frozen before each search executes. No threshold, candidate
pool, budget or model is changed in response to the evaluation results. These
are authored models from an already explored family; some widths were used in
previous development. This is not an independent project or campaign holdout.

## Actual outcomes

| Budget including baseline | Price order | Legacy learned order | Centered learned order |
| --- | --- | --- | --- |
| 2 | No verified feasible selection | No verified feasible selection | Width 0.50 m |
| 6 | No verified feasible selection | No verified feasible selection | Width 0.50 m |

Price order was run separately with each policy. Both executions agree. The
centered policy places widths 0.50 and 0.52 m first, followed by the predicted
infeasible alternatives in price order. The legacy policy predicts every
alternative to pass and keeps price order. The baseline fails the strain limit.

The subsequent exhaustive comparison verifies widths 0.48, 0.50 and 0.52 m as
feasible. The finite-pool minimum is **0.48 m / 159.3108 synthetic price units**;
the centered selection is **0.50 m / 162.9108**, leaving a **3.6-unit gap**.
The centered policy has no false-safe predictions in this pool, but incorrectly
predicts 0.48 m as infeasible. The legacy policy has five false-safe predictions.
Actual reanalysis prevents those predictions from becoming accepted selections.

The original three reports without an oracle retain their null oracle/error/cost
gap fields. The audit separately attaches the later common oracle to all four
frozen plans; it does not rewrite their original results. A missing selection
retains a null cost gap, not zero. The 3.6-unit difference uses the declared
concrete/straight-longitudinal-rebar estimate and is not a verified market quote.

Budgets are fixed candidate counts, not stopping times. The budget-2 centered arm
executes the same 32 core calls as its price-order arm, with 82 versus 86 Newton
iterations/linear solves. At budget 6 both arms execute 96 core calls and 254
Newton iterations/linear solves. These observations do not establish an
end-to-end speedup, particularly with training, feature work, audit and I/O
costs included. The larger centered shortlist still misses 0.48 m; simply
increasing this budget from 2 to 6 does not improve the selected estimate.

## Work, verification and failed setup

The completed comparison executes **47 result rows, 94 full-path invocations,
752 core calls and 1,984 Newton iterations/linear solves**. This comprises
96 training, 512 online and 144 oracle core calls, and two completed fits.
All 47 original fresh full-path verifications pass and report 376 checked
response reassemblies. These counts contain repeated baseline/candidate models;
they are not 47 independent structures. The six CLI processes take
51.688326995 s in their parent timer, excluding source-snapshot preparation.
Single fixed-order shared-host timings are observations, not a speed benchmark.
The strain-boundary case has no observed steel plastic accumulation or concrete
damage and does not validate plastic collapse or missing shear/bond mechanisms.

The first execution snapshot mistakenly copied only Python files and omitted
packaged checkpoint JSON Schema resources. Three training analysis invocations
raised, no fit completed, and their execution work remained unknown. That attempt
and its 2.097861975 s parent record are preserved separately. The corrected
execution copies all 436 tracked Python-package source/resource files and binds
them to Git. Inputs and the prospective protocol remain byte-identical. **752
is the known completed-experiment count; it excludes the failed attempt's
unknown work and is not the total cost of the whole development task.**

The audit checks every frozen source/resource against Git, 376 comparison
artifact references against original bytes, report/policy/plan logical hashes,
the exact shared training samples, known work counters and original verification
records. It reconstructs both fits with independent augmented least squares,
checks ridge stationarity, and recomputes original and post-hoc cost/coverage
audits. No additional Newton solve or fitted policy is produced by the audit.
The original numerical executions perform the fresh solver verification; the
later audit does not claim to execute it again or provide external validation.
Two audit-script corrections (a nested claim field and unordered arm membership)
are retained, along with their failed logs. Original solver reports are unchanged.

Local verification passes **38 candidate-search tests** (11.35 s) and
**23 candidate-cost tests** (1.51 s), plus Ruff, scoped mypy and diff checks.
Tests compare the centered fit with augmented least squares, check response-shift
and exact-constant behavior, reject unsupported methods before label generation,
and preserve an original legacy policy's dictionary/hash. The actual CLI study
also exercises both fitting choices. These focused checks are not the full suite.

The [machine summary](rc-candidate-boundary-20260910.summary.json) includes phase
costs, both fitting results, all frozen shortlists, failures, cost gaps and the
prior failed-attempt binding. The completed packet is
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-candidate-boundary-corrected-ga7fbf35`:
1,161 files / 30,426,729 bytes; sibling inventory SHA-256
`ddffa25c908719336d52188a4a0ab2229bdbf88f131932f891f4c29925fa2741`.
Every retained file is reread and hash-checked before sealing.

The next useful question is whether a policy can prioritize uncertain cheaper
candidates near the performance boundary without losing the small-budget
feasibility benefit. That needs another prospective experiment; this observation
does not establish the improvement. The earlier runtime-initialization study
still selects secant, and this candidate-ranking result does not change it.
