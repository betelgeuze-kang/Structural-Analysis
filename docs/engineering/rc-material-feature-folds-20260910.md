# Committed material inputs: retained negative case-transfer result

Source `b08b51cde7af2a1f36d6f05bbdba063f3720863a` adds the experimental
`accepted-fiber-state-secant-correction.v1` profile and explicit v4 policy.
It appends ordered native concrete/steel state fields to the original legacy
features. Geometry, coordinate history, targets, correction units, ridge and
range margin remain unchanged in this comparison. The earlier normalized-history
profile is a separate experiment and is not combined with this change.

These inputs are **solver-computed internal states**, not measured experiment
channels. Public drawings, reinforcement/material definitions and sensor/loading
correspondence still need reconstruction before experiments enter learning.
No external training sample or independent validation credit is created.

## Runtime and original-record binding

Each opt-in arm extracts its own already accepted checkpoint before making the
next proposal. Constant-loaded arms use the actual preload at the first target.
Member, integration-point, fiber and native field order are explicit; checkpoint
and problem hashes identify the source. The snapshot is detached immutable JSON.
Its extraction wall/CPU time is retained per entry and included in whole-path
cost. It performs no new material integration or structural solve. Serialization,
imports and other path work remain included in the wider path/study clocks.

The profile records every native concrete tensile/compressive history strain,
damage and dissipated energy field, and steel plastic strain, backstress,
accumulated plastic strain and dissipated energy field. Units remain those of
the native state: strain/damage are dimensionless, backstress is MPa and energy
density is MJ/m3. Training-only mean/scale preprocessing handles their numerical
scales; no invariance across arbitrary unit systems is claimed.

Policies bind material-field order, model/solver/DOF identities and arithmetic.
Missing or mismatched snapshots abstain; reference-solver acceptance and existing
fallback behavior remain authoritative. Existing feature profiles, defaults and
absent-field serialization remain supported. The new profile rejects unsupported
native layouts and more than 2048 material fields / 2200 total features before
learning-study execution. This is a bounded experimental representation, not a
general cross-topology model.

The derivation utility can recover these inputs from an existing training label's
original **parent** checkpoint. It checks original sample/step identities, source
features, original correction coordinates and the native checkpoint against the
same compiled problem. Validation/holdout rows reject before original-step access.
Content hashes establish consistency, not independent source authentication.

## Fixed observation on the existing 964 training pairs

The original expanded-study inventory is verified before copying 976 selected
original files: plans, four training models/requests, training samples/policy and
964 original reference steps. Evaluation declarations are present in the original
plans, but evaluation response files are not read. All 439 retained source/schema/
selected-test files match Git before and after the observation.

The four authored training cases contribute 241 pairs each. Each input now has
**500 features**, including **408 native material scalars**. One fixed fit uses
all 964 pairs; four case-withheld fits each use 723 and withhold 241. Ridge remains
`1e-6`, range margin `0.1`; there is no parameter search or automatic retry.

| Withheld case | Eligible / 241 | Learned/secant correction RMSE range |
| --- | ---: | ---: |
| train-a | 0 | 33.282-350.012, ungated diagnostic only |
| train-b | 241 | 45.390-216.249 |
| train-c | 0 | 766.219-3397.910, ungated diagnostic only |
| train-d | 0 | 27.432-237.601, ungated diagnostic only |

Each range spans six separate non-controlled augmented coordinates in their
original solver scaling. Values above one are worse than secant. No mixed-unit
aggregate, runtime speedup or structural-response accuracy is inferred.

The new candidate is **not promoted**, and the unchanged candidate is not admitted
to another expensive full-path evaluation. Coverage does not improve and every
non-controlled error worsens in the only eligible case. Individual-feature range
checks alone do not establish useful joint feature support or prediction quality.

A separate audit reproduces all 964 parent input vectors, original labels and
legacy feature prefixes, and all four reported withheld RMSE arrays exactly.
Fold means/scales/bounds use only that fold's training rows. Training-coordinate
RMSE ratios are 0.373-0.715, while withheld errors increase sharply. This is a
strong transfer failure for this representation and fixed estimator.

The regularized normal-system condition estimates are about `1.05e11-1.07e11`;
relative stationarity residuals are `9.39e-12-1.31e-11`. These diagnostics do not
prove numerical conditioning irrelevant or identify one cause. Joint support,
regularization and estimator stability need training-only evaluation alongside
independently diverse physical cases. More native fields alone did not improve
transfer on this corpus.

## Costs and verification

There are **five fits, zero new structural solves and zero material integrations**
in this observation. Original numerical labels retain their previously recorded
generation costs; they are not newly free training data. The worker forbids solver
dispatch and native steel/concrete integration during this derivation/diagnosis.

Model preparation takes 0.021454 s, original-step reading 0.121318 s, derivation
33.715374 s and the full-training fit 0.040618 s. Four fold fits take 0.026393,
0.029447, 0.028118 and 0.028250 s, nested in the 0.730426 s diagnostic.
Worker time through reports is 37.855143 s (CPU 37.842071 s), nested in parent time
38.268458 s; peak worker RSS is 726180 KiB. The additional original audit takes
3.835880 s internally (CPU 2.728137 s), with peak RSS 2480636 KiB. Audit imports,
source/input preparation, tests, GitHub retrieval and sealing have separate scopes;
these are not exclusive-host performance measurements or total project cost.

The final relevant test selection passes **96 distinct tests**: 64 in 98.28 s and
32 in 6.51 s. The earlier two material tests in 37.88 s overlap. Tests cover actual
constant-preloaded learning paths in binary64 and retained arithmetic, exact parent
inputs, unchanged original corrections, missing/reordered snapshots, no-integrate
derivation, wrong-parent/evaluation-row rejection, and withheld changes leaving
that fold's fitted policy unchanged. Ruff, four-source mypy and diff checks pass.
These authored tests do not establish external physical accuracy.

Worker, parent and audit processes are terminal/absent before sealing the packet:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-material-folds-cc9g9069`.
It contains **1441 files / 352537623 bytes**, inventory SHA-256
`c9cddfaa140fe71196904da9f3ad4b01500bda733ad687e172c2482e00e545c2`.
All files are reread exactly; sealing takes 0.531177 s. The
[machine summary](rc-material-feature-folds-20260910.summary.json) retains the
protocol, fold metrics, costs, verification and seal identity.

At preceding published head `86bc0bbfb`, main CI and all four Python shards stop
at exact-source evidence materialization with
`external_code_to_code_product_replay_not_passed` and
`external_code_to_code_technical_receipt_not_ready`; their original logs are
retained separately in this packet. Issue State's offline job passes while
`live-exact-main` is skipped. PR #440 remains open, draft and unmerged at
`f788a3c55964ef963f8145835e188d4a3f3792da`. None of these observations closes
independent verification, current-main integration or the full roadmap.
