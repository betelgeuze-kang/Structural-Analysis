# Predeclared runtime selection from 165 retained training labels

This campaign tests whether the [two new interior training groups](rc-interior-training-coverage-20260920.md)
produce useful learned starts on whole nonlinear paths. It does not infer speed
from reference-parent range coverage. All existing acceptance tolerances and
the 1% minimum improvement rule remain unchanged.

## Frozen protocol

- Source: `80f9ff404dfa15f7048c21d673f348155f90d965`.
- Original 99-label inventory: `f850f7e65670bf4d6254039da2aca35269cbd1840b645d82308c2402017849f0`.
- New 66-label inventory: `23d28a47d891e1b45d7306007529a78d203a436677af0fd5fe9e7dbe4061af92`.
- Fifteen training cases form five whole geometry/history groups of three amplitudes. Two reserved cases remain declared and unexecuted.
- Fixed ridge values 10,000 and 1,000,000; three counterbalanced repetitions. This schedules **90 fold comparisons and 360 full paths**, including fresh reference checks.
- Every held group removes all 33 of its samples; a fold fits only the other **132**. All 165 original sample hashes, contexts, features, corrections and model/request bindings are checked before execution. No structural labels are regenerated.
- Selection budgets: at most 31 fits and 6,840 core calls, including possible proposal/secant retries. An additional pooled metadata fit is measured separately; its weights/scales are not used in withheld-group fits. The runtime selector explicitly refits complementary groups.
- Existing static model abstention is enabled, with secant as fallback. Material capture, proposal work, complete path time and static-gate overhead remain accounted for. Failed or unknown work cannot grant a speed ratio or policy promotion.
- Arithmetic remains `retained-twofold-refinement.v1`. No solver tolerances, material laws, load histories or line-search factors change.

The two source label-study intervals and their work counts are retained separately
and counted once in the protocol. They are not the entire development history's
research cost. Pooled fit, selection and parent time are recorded separately;
no total net savings or independent-project claim follows from a fold score.

## Confirmed execution state at this record

The frozen source preflight passes: 17 cases, 165 samples, five groups, zero
preflight fits and zero solver calls. All 469 archived source files match their
Git blobs; all previously archived generation dependencies remain byte-identical.
The actual execution has written its plan and first completed fold receipt.
It was confirmed live as process **212775**, observed through unified shell
session **31748**. No final result or selected strategy is available yet.
Continue observing this handle; do not launch another copy because observation
takes time. The final process receipt will be written only after termination.

Packet:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-pooled-runtime-e5ho6__o`.
Selection plan hash:
`sha256:ea6e9eb4c420ec2c8fa079de72bea03681fb36e45f387ebedf5c28cf2cb58730`.
The initial pooled metadata fit took 0.025927342 seconds and is explicitly not
promoted. The driver is `scripts/run_rc_pooled_runtime_campaign.py`.

After termination, audit the exact fold roster, each complementary sample set,
all four accepted paths, original comparisons, decision counts, known work,
selection arithmetic and separate label/fit costs before reporting any outcome.
Neither a partial favorable fold nor a lower coordinate error establishes the
required full-path benefit. Existing secant selection remains authoritative
until the complete new experiment supports a different result.
