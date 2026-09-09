# RC training coverage expansion, 2026-09-10

The retained learned correction remains slower than deterministic secant. Before
changing the learner, a train-only diagnostic reads the 482 original paired
samples from the first sealed repetition. It reads no validation or holdout
response. Linear, history-augmented linear and five fixed-bandwidth Gaussian
kernel fits are explored at ridge `1e-6`.

In-sample normalized squared error relative to zero secant correction is 0.7525
for the original linear fit, 0.7116 for eight additional history descriptors and
0.0266-0.4748 for the kernel fits. These are fitting diagnostics, not speedups.
Leaving one training geometry out produces larger raw regression error, but
**all 241 rows in each direction are outside the original policy's training
box**. The deployed policy would abstain; these forced extrapolations do not
measure accepted-proposal performance. Both original geometries belong to one
authored training project and history, so these are not independent project
folds. No alternative learner is admitted by this diagnostic.

Forty-eight exactly constant input columns also exhibit small nonzero standard
deviations from floating-point reduction. Exact constant handling leaves the
linear diagnostic error effectively unchanged. It is not adopted as a claimed
performance fix. The raw diagnostics, protocols and source hash are retained at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-train-feature-audit.vit8e50_`.

## Frozen data-only experiment

The [complete input plan](../../examples/rc_learning_training_expansion_20260910/plan.json)
adds two authored training cases to the existing two:

| Case | Horizontal/vertical member lengths (m) | Negative/nonnegative target factors |
| --- | --- | --- |
| train-c | 1.75 / 2.50 | 0.9 / 1.1 |
| train-d | 3.25 / 1.25 | 1.1 / 0.9 |

The two lengths vary independently, expanding beyond the original shared
`vertical = horizontal - 0.5` training relation. The factors transform only
train-a's existing authored target sequence, preserving all 242 target positions.
Materials, reinforcement, support conditions and Newton settings are unchanged.
The existing two training inputs and both development evaluation inputs retain
their original bytes. All six model/request pairs are included for reproducibility.
Project/family identifiers remain authored partition declarations. These inputs
are not new public experiments or an independent corpus.

Numerical source stays frozen at `bdfa9a0262cf6fb74d27a7914744487178c5f150`:
433 copied source files match both their retained SHA-256 identities and Git
blobs. The original retained-twofold arithmetic, ridge `1e-6`, OOD margin `0.1`,
arm order, fixed comparisons and fallback behavior remain. New full reference,
secant and fresh paths generate every training label; no label-generation cost
is omitted by reusing the earlier samples. Fitting precedes both evaluation
paths. Existing validation/holdout cases have been observed before and are
explicitly development reuse, not a newly blind test.

All six cases pass the original split/model preflight, which compiles six models
without a Newton call. The planned complete observation comprises 20 paths,
4,840 target solves before rejected retries and 964 eligible training pairs if
every required training path passes. Generation, fitting, inference, recovery,
rejected attempts and parent elapsed costs remain recorded by the original
study runner. No automatic retry or repeated-study admission is enabled.

The prepared execution root is
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-training-expansion.vdyyju94`.
Original-record verification and fixed physical comparisons are required after
execution; a completed process alone is insufficient. This protocol does not
claim a trained expanded policy, improved runtime or roadmap closure.

The [startup observation](rc-training-expansion-started-20260910.summary.json)
records the original launched worker and live process check, bound to committed
input plan `b0d7e284ec7891bde989cf46607a0732af7af803`. The subsequent
[completed observation and audit](rc-training-expansion-completed-20260910.md)
finish all 20 paths and verify 964 train pairs, 4,840 original steps and 484 policy
decisions. Every fixed comparison passes, but validation remains slower than
secant and OOD still abstains throughout. The startup snapshot is historical;
the completed report retains full costs and does not admit automatic repetitions.
The [training-only diagnostic summary](rc-training-feature-diagnostic-20260910.summary.json)
retains all 24 regression fits, raw errors and OOD counts. Its source training
sample file matches the prior sealed inventory; none of the original studies
is modified.
