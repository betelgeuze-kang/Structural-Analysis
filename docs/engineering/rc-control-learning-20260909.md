# Train-only learned proposals for experimental cyclic RC control

`run_rc_control_learning_study` connects full original RC control analyses to an
immutable ridge correction of the existing secant initial iterate. The original
Newton, material, equilibrium, increment, control, parent and rollback authority
is unchanged. This is a separate cyclic-control profile; the monotonic-load
learning input/policy is not relabeled or reused as cyclic training evidence.

Every case carries a detached canonical model, exact typed control request,
caller-declared project/geometry-family/history identities and a train, validation
or holdout label. All cases are compiled and screened before creating output or
producing labels. Declared identities and entity-name-invariant physical/geometry
hashes cannot cross splits. Geometry is screened independently of changed loads,
sections or materials. Amplitude/sign-normalized target sequences and complete
prefix aliases also cannot cross splits. The frozen observation source uses 12 significant digits for the history
screen and does not generally group rotated/translated geometry. The later
strengthening described below also screens normalized shape distances, resampled
turning points and partial-leg prefixes. These conservative checks do not
authenticate project or family provenance. Authored development labels are not independent projects.

Only train cases are analyzed before fitting. Each runs separate reference,
secant and fresh reference paths, with complete original recovery and retained
costs. Only an exact complete reference repeat supplies labels; a failed secant
comparison does not invalidate those original reference labels or become passing
evidence. Training pairs contain the original accepted coordinates minus the
secant predictor, original step byte hash, immutable parent and own accepted-prefix
context. No evaluation labels or future response labels enter features, fitting,
preprocessing, OOD limits or hyperparameter selection. The first target abstains
because no prior accepted increment exists.

Features combine pre-analysis model declarations, the current target/increment,
previous increment, accepted-prefix length, current augmented coordinates and
previous coordinate increment. Mean, scale, target scale, limits and ridge weights
use only train rows. The frozen finite JSON policy binds the model feature layout,
free-DOF order, controlled coordinate, solver configuration and original training
sample hashes. Duplicate JSON keys, malformed/boolean numeric arrays, invalid
scales, dimensions and hashes are rejected. Hashes establish consistency, not
source or training-data authentication.

Evaluation begins only after the policy is frozen and uses the existing independent
reference/secant/proposal/fresh-reference benchmark. An incompatible or OOD input
returns to the parent start; inference cannot commit a physical state. Prescribed
control is imposed only on the proposed initial coordinate. All other acceptance
conditions remain in the original solver. Policy identity is checked after each
evaluation and every proposal/abstention is recorded. Generation and evaluation
known/unknown core, Newton and linear costs are separate; fitting and whole-study
CPU/wall include the actual phase work. The whole study includes all generation
arms, full verification, fitting, inference, recovery and I/O, excluding the final
report write. Failed generation retains the roster and skips fitting/evaluation;
a fit failure retains generation costs and marks evaluation not attempted.

The original implementation validation passed 198 related tests, including 13 new learning tests, actual cyclic
label generation, actual proposal entry, OOD abstention, split aliases, train-only
statistics, immutable policy decoding, unknown generation work and fit failures.
The initial development run had one incorrect test expectation: a nearby geometry
was inside its explicitly extended OOD margin. A farther held-out test geometry
now tests actual abstention; the policy admission rule was not changed. The
original failed test log is retained. Ruff and diff checks pass. These are local
implementation checks, not full-repository or independent physical acceptance.

A separate frozen observation uses two authored training geometries and two
authored evaluation geometries with distinct declared control-history shapes,
all 242 targets and the same shared terminal finishing profile. Three serial fresh
processes are predeclared with alternating strategy order. Each repetition charges
its complete training generation and fit again. The existing unpolished and
shared-finishing strict-tolerance failures remain unchanged. Cyclic learning does
not waive those physical tolerances or license independent provenance, design
approval, net acceleration, public API expansion or release claims.


## Completed frozen full-path observation

Source `889e78c2b22e1d6f8d6633993834fac83fc8ac44` is copied into an isolated
409-file Python tree and rechecked unchanged. The new observation root is
`/tmp/structural-rc-cyclic-learning.4o9kllw_`; its four typed cases pass the complete
split preflight before numerical execution. Training uses the authored 2.0/1.5 m
and 3.0/2.5 m L-frames, validation the 2.5/2.0 m frame and OOD holdout the 6.0/4.7 m
frame. All histories have 242 targets and two reversals. Training uses the original
-0.02/+0.02/-0.02 m extrema; validation uses -0.018/+0.016/-0.014 m and holdout
-0.014/+0.022/-0.010 m. The explicitly synthetic partition labels are not real
independent project or family provenance.

Three serial fresh processes completed full generation, fitting and evaluation
with alternating arm orders. All **42 paths complete 242 targets**: 10,164 original
core entries and 36,672 Newton/linear counts, with no failed numerical attempt or
unknown execution work. Each repetition charges 1,452 generation core entries /
5,572 Newton-linear counts and 1,936 evaluation entries / 6,652 Newton-linear
counts. Ridge `1e-6`, OOD margin `0.1`, shared terminal polishing and the original
`1e-10` absolute / `1e-8` relative physical comparison tolerances stayed fixed.

Each fresh process independently generated 482 training pairs and fit a policy.
All three complete sample artifacts and policies are identical. The policy hash is
`sha256:2d2087433c9b137ff888784389db183956d856363e427aa63dfc9ed84b769a05`.
Training targets came only from the two train cases; each case/strategy's three
response histories reproduce exactly, and every reference/fresh-reference history
and native terminal checkpoint is byte-exact. Fitting median time is 0.008402 s;
whole-study median is 499.078 s with sample SD 4.471 s. The serial parent records
1,502.720 s, excluding source staging. Fit time alone is not total AI cost.

| Evaluation | Reference median ± sample SD (s) | Secant (s) | Learned arm (s) | Learned full-history pass |
| --- | --- | --- | --- | --- |
| 2.5 / 2.0 m validation | 39.270 ± 0.385 | 29.572 ± 0.243 | 32.261 ± 0.289 | 0 / 3 |
| 6.0 / 4.7 m OOD holdout | 31.486 ± 0.329 | 25.992 ± 0.140 | 31.505 ± 0.277 | 3 / 3, entirely reference abstention |

For each validation repeat, the first target abstains and all 241 later learned
proposals enter and complete the original solver. The learned arm needs 813
Newton/linear counts versus secant's 698 and reference's 1,046. It is slower than
secant in all three observed pairs and fails the fixed full-history comparison
at 1,161 force/reaction/section values per repeat. Secant also fails, at 1,268
values. No learned acceleration is accepted.

For each OOD repeat, every one of the 242 proposals abstains to the reference
parent start. The learned arm therefore has exactly the reference history and
829 Newton/linear counts; the secant arm has 562 counts but fails physical
comparison. The OOD pass confirms fallback preservation, not learned
extrapolation or independent generalization. All older strict-tolerance failure
observations remain intact.

## Original-record audit and strengthened split admission

The no-solve audit checks 10,164 original started/outcome/step records and commit
gates, 1,446 training-pair records (482 unique pairs repeated three times), 1,452
frozen-policy predictions, own-prefix/parent ancestry, report/path/sample hashes,
train-only preprocessing and the ridge normal-equation residual without refitting.
It independently recomputes every full-history comparison, mismatch summary and
terminal-identity flag. All 409 frozen source files match both their manifest and
the original Git blobs at `889e78c2b2`. The frozen source is distinct from the later
preflight improvement; the raw experiment was never switched to the new code.
[Source-bound audit, complete plan and raw inventory](rc-control-learning-20260909.summary.json).
The sealed local bundle contains **61,558 files / 2,981,549,537 bytes**. Every
file was reopened and its size/hash checked against the sorted inventory; inventory
SHA-256 is `c8d579e95c9b8612a3287da367cb0d961dc5d493c501bd62918335970b2d1e91`.
The inventory and its verification receipt are outside the sealed root. These
local hashes are consistency evidence, not independent authentication or hosted
raw-artifact retention.

[Stronger split screens](rc-control-learning-split-screen-20260909.md) subsequently
reject transformed/scaled geometry, resampled turning-point histories and prefixes
ending inside a monotone leg before any output or label production. The original
four observation inputs also pass this stronger screen; that post-observation
consistency check does not turn their synthetic project/family labels into
independent provenance. After all numerical workers exited, **217 related tests
pass in 35.73 seconds**, including actual fitting and proposal evaluation under
the stronger preflight. Earlier 198-, 32- and five-test groups overlap this work.
Ruff and diff checks pass. A prepared full-repository Python suite and current-head
hosted acceptance remain unproven; independent corpus, numerical error-budget work,
licensing/hardware/owner gates, current-main R1 and separate R2 remain open.
