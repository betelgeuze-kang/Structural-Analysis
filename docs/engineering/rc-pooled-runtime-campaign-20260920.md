# Completed runtime selection from 165 retained training labels

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

## Historical execution observation (superseded by completion below)

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

## Historical auditor preparation

`scripts/audit_rc_pooled_runtime_campaign.py` now checks the full 90-fold roster,
the 132-sample complementary policy identities for every held group, all four
complete paths, the original comparison tolerances, static-gate identities and
timing, invocation work and the equal-case selection score. It also binds each
comparison directly to the plan's exact model, complete request and source
revision, preventing a result from another case from satisfying the audit.
Selection fits, the additional pooled fit and the two historical label-study
costs retain separate receipts. The auditor runs no solver or fitting code.

At auditor revision `ba340f66224e97dba1c2559920fd72e810369581`, focused timing and
transplanted-case rejection checks pass **5 tests in 1.66 seconds**. The source,
model and request binding check also passes on the first original completed
comparison. The full audit has not run because the campaign is still live;
16 completed fold receipts were observed at this point. This observation is
not a final selection result or an efficacy claim. Auditor source copies and
their hashes are preserved separately in the active packet's `audit-source`
and `audit-preparation.json`, leaving the frozen numerical source unchanged.

## Completed and audited outcome

The original process terminated successfully. The complete audit passes without
new fits or solver calls. All **90 comparisons and 360 full paths** pass the
original history checks. Every excluded group fits only its complementary 132
samples. There are **594 proposals, 486 abstentions, 4,680 core calls and 24,054
Newton iterations/linear solves**. Static gates reject 36 folds (groups A/C);
54 folds in B/D/E allow proposals.

| Ridge | Equal-case mean learned/secant time ratio | Selection |
| --- | ---: | --- |
| 10,000 | 1.0164304666296753 | Rejected |
| 1,000,000 | 1.0270367268299982 | Rejected |

**Secant remains selected.** Neither candidate meets the unchanged 1% improvement
requirement. No active-proposal case is faster in all three repetitions. The one
case consistently faster with ridge 10,000, C-amp100, contains zero proposals;
its fallback timing variation is not an AI gain. D-amp100 and D-amp150 have
slightly favorable means for that ridge but inconsistent repetition outcomes.
More eligible training coverage has enabled more actual proposals, without
establishing useful full-path acceleration. Earlier and current aggregate scores
use different case mixes and must not be treated as a controlled improvement.

Selection takes 1,634.134640853 seconds. Its 30 fits total 0.702777347 seconds;
the additional pooled metadata fit takes 0.025927342 seconds. Driver parent time
is 1,634.991634764 seconds; outer process time is 1,636.396386288 seconds. These
nested intervals are not added together. The two prior label-study intervals
remain separate at 134.743465748 and 86.013788545 seconds. No final full-pool
refit or policy promotion occurs, and both reserved cases remain unexecuted.

The packet retains the original live observation and auditor preparation, and
adds `receipt-audit.json`, `audit-completion.json`, and an immutable payload
inventory. The [machine summary](rc-pooled-runtime-campaign-20260920.summary.json)
contains its inventory hash, byte/file counts, exact result hash, all case-repeat
scores, work counts and separate costs. Audit revision is
`ba340f66224e97dba1c2559920fd72e810369581`; numerical source remains unchanged.

Next work should isolate proposal/capture overhead and iteration savings from
these retained receipts before training a new strategy selector. Divergent
full-path states cannot be spliced into same-parent causal training labels.
Independent validation, concrete-field convergence and useful AI benefit remain
open; this completed experiment closes none of those requirements.

The [completed retained-cost diagnosis](rc-pooled-runtime-costs-20260920.md)
now isolates roughly 22–24 ms proposal and 55–56 ms capture overhead per active
path. New D cases sometimes save invocation work, but no consistent total-path
gain is established. No additional solve or fit was used for this diagnosis.
