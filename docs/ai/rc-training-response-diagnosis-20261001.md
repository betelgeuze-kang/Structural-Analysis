# TRAIN response diagnosis and comparator contracts

This follow-up isolates a numerical comparability limit and repairs two software
comparison contracts. It does not qualify the learned warm start, admit experimental
data, or establish independent physical accuracy or service readiness. The full
Structural Analysis roadmap remains active.

## Source and evidence boundaries

The completed E04 numerical campaign executed source
`135ead5438f99cd33fb9996d2539c7e9b942811c`; its later documentation commit
`79c44d9ac379261541c46f2c99074e77ddb776de` is not another numerical execution.
This diagnosis reads selected TRAIN originals only. Validation and holdout numerical
outcomes are not used for tuning, fitting, or this diagnostic comparison.

The separate polishing micro experiment executes source `79c44d9a` before the
comparator repairs. Its frozen plan is
`sha256:8ba56d49756bbdbecf651f9ae10ffb9588b139d7e88fb737bb5acefe26e67ce6`.
Current repaired software is tested as an explicit two-file working-tree patch
over that parent; the final publication bridges the tested bytes to Git blobs.
There is no numerical rerun at the later publication commit.

Host originals and receipts are retained under
`pr-backlog-20260929/full-training-numerical-followup-20261001/train-response-diagnosis-20261001/`
outside Git. The quantitative, solver-source, micro-execution,
post-fix-pure-replay, root-whole-module-verification-01, and packaging-01
directories preserve their separate scopes. These paths describe local evidence,
not GitHub-hosted originals or signed producer/hardware authority.

## What the preserved TRAIN comparisons show

Twenty selected TRAIN samples have sixty original repeated comparison reports.
Their 180 arm comparisons contain 194,940 numeric scalar comparisons and 861
failures, representing 287 distinct case/target/arm/scalar locations repeated
three times. Failures are confined to forces (426, N) and moments (435, N m):
342 member-end forces, 219 member-end moments, 216 section moments, and
84 support reactions. Section axial force, curvature, strain, fiber strain/stress,
and displacement families have no failing scalar in this selected scope.

All failures are dominated by the unchanged absolute term, with
`atol=1e-10` and `rtol=1e-8`. The largest mismatch-to-allowance ratio is
88,462.9735 at a near-zero B1 proposal end force: reference
`1.1368683772161603e-10 N`, proposal `-8.854016186887748e-6 N`.
The largest failing force and moment magnitudes remain about `1.0621e-5 N`
and `4.7706e-6 N m`. Their small size is not a declared engineering zero
threshold or proof of harmless roundoff. No tiny reaction is clipped.

Source recovery uses the same original parent and final Newton coordinates,
with fresh assembly/accepted-checkpoint equality. The inspected near-zero
reaction difference agrees with the stored assembly after the existing kN-to-N
projection. Large opposing quadrature contributions and distinct accepted
binary64 endpoints remain plausible numerical mechanisms; a reporting-unit or
commit/rollback defect was not established. Equilibrium convergence and full
response comparison use different gates. A mixed-unit maximum is not a physical
accuracy criterion.

The original TRAIN label roster remains **19 unknown, one negative, zero
positive**. Unknown rows remain in the denominator. The negative is abstaining
fallback overhead, not a learned correction benefit. E04 full-path eligibility
remains **0/18**, with performance ratios null.

## Bounded terminal-polishing micro experiment

Four authored TRAIN cases use their fixed original parent at source target index
1, with three repeats each. The typed request changes only
`newton.terminal_polishing: false -> true`; models, complete original target
definitions, tolerances, and other solver settings are frozen. Counterbalanced
reference/secant orders and a fresh reference are fixed before execution.
No proposal, seed, gate, fit, or validation/holdout case is used.

| Case | Response comparisons passing | Fresh reference exact |
| --- | ---: | ---: |
| A | 0/3 | 3/3 |
| B | 3/3 | 3/3 |
| C | 0/3 | 3/3 |
| D | 0/3 | 3/3 |
| Total | 3/12 | 12/12 |

This is B's three repeats at source target **1**, not target 3. Singleton
diagnostic paths have local target index 0. All paths complete, but completion
does not replace response comparison. The supplied original prefix is not
reexecuted or authenticated as part of this local one-target experiment.

Actual work is **36 native calls, 252 Newton iterations/linear solves, zero
fits**. The 252 solves comprise 228 primary plus 24 accepted polishing solves.
Twelve rejected polish attempts stop at the strict residual-improvement check,
after a candidate assembly and before an additional linear solve. Independent
read-only auditing confirms 577 checks and unchanged 338 original files.

The owned supervisor completes with all children reaped and no unknown work.
Its enclosing wall is 9.967806371 s; retained result files occupy 14,364,228
bytes. This scope includes its guards and child/output work but excludes its
final receipt write. Nested clocks and prior E04 work are not added. These are
local observations, not hardware/filesystem attestation. Polishing alone does
not resolve comparability across these four cases or demonstrate whole-path gain.

## Two comparator contract repairs

`_numeric_payload_difference` now explicitly distinguishes boolean values
from numeric values, including NumPy scalars. Equal genuine booleans remain
compatible; `true` versus `1` and `false` versus `0` are rejected instead of
passing Python's fallback equality.

Generalized displacement snapshots now use their reported symmetric predicate,
`abs(left-right) <= atol + rtol * max(abs(left), abs(right))`, through the same
numeric payload helper. The previous `np.allclose` branch scaled relative
tolerance by the right-hand value. At the exact dyadic example `73/64` versus
`1`, `atol=0`, `rtol=1/8`, the previous branch changed verdict when operands
were swapped; both directions now satisfy the declared predicate. Existing
maximum-difference reporting is preserved.

These software defects are not established as the cause of E04's force/moment
failures. Pure replay of all sixty selected TRAIN reports and twelve micro
reports preserves their original verdicts, diagnostics, maximum differences,
19/1/0 labels, and 3/12 micro result. It executes zero new native calls,
assemblies, or fits and preserves all 367 read originals. It does not exercise
a new numerical campaign or qualify generalized-displacement physics.

Four complete related modules pass **209 tests**, with zero failures/errors/skips:
`test_fiber_frame_runtime_strategy.py`, `test_fiber_frame_runtime_benchmark.py`,
`test_rc_control_warm_start.py`, and `test_rc_control_parent_step.py`.
Ruff lint/format and whitespace checks pass. The 8,922 tracked actual source
paths match before/after testing. Focused owner and external reproduction
subsets overlap and are not added to 209; historical 25/560 checks retain
their original source identities. Existing test function ASTs are unchanged;
formatting of the owned test file and six new test functions are explicit.

A fresh offline copied-source build verifies 494 inputs, all 497 wheel members
and RECORD entries. Isolated imports load every used structural module from
that wheel; eight pure probes check boolean separation and the symmetric numeric
helper. No dependency or wheel is installed, and no solver is run by this
package check. The wheel matches the tested patched source; it is not a
deployed-service or independent physical validation result.

## Next decision

Keep the zero-positive guard and all unknown rows. Inspect the already completed
precision, strain/stress, coordinate, and force-accumulation diagnostics before
declaring another TRAIN-only protocol. Any fresh numerical experiment needs
frozen source/roster/requests and native/time/disk budgets, unchanged comparison
criteria, and full attempted work accounting. Do not tune the frozen pair from
validation/holdout outcomes, clip near-zero responses, or waive failed gates.
Independent experiment correspondence/rights, learned total-cost benefit,
final-head CI/main integration, hardware conditions, and release authority
remain open.


## Fresh complete-path TRAIN precision diagnosis

The separately frozen follow-up ran once at numeric source
`7cfc16fcab78b661f17bb6435fdecbe5db7127ed`. Four authored TRAIN cases
A/B/C/D, three repetitions and two arithmetic profiles produced 24 comparisons
and 72 complete six-target paths. Every arm started from its own new native
initial state; no original checkpoint or teacher policy was reused.

| Instrumented profile | Full-response eligible comparisons | Native invocations | Newton / linear solves | Disjoint comparison wall time |
| --- | ---: | ---: | ---: | ---: |
| Matrix / binary64 control with terminal polishing | 0 / 12 | 219 | 1,761 | 45.942 s |
| Coupled retained precision, terminal refinement limit 1 | 12 / 12 | 219 | 1,845 | 141.624 s |

Both profiles used the same original physical model, material, loads, six targets,
14 explicit line-search alphas, solver iteration limits and typed
`terminal_polishing=True` request. The comparison criterion remained absolute
`1e-10` plus relative `1e-8`. The precision profile used exact-rational strain,
twofold coordinate increments, retained material strain and coordinates,
rational force accumulation and terminal twofold refinement with limit **1**.
It is distinct from the existing `retained-twofold-refinement.v1` learning
profile, whose terminal refinement limit is **2**.

All 24 reference/fresh-reference repeats matched exactly. A declared physical
response tolerance pass does not imply secant checkpoint byte equality. No seed
proposal, gate, fit, validation/holdout numerical evaluation or original-label
revision ran in this follow-up. E04's 19 unknown / one negative / zero positive
labels and ineligible final comparisons remain unchanged.

Actual work was 438 native invocations: 432 committed and six rejected seeded
attempts. Newton and linear work was 3,606: 3,258 primary plus 348 accepted
polishing solves. The 84 rejected polishing candidates stopped before another
solve. Original assembly dispatch records counted 10,686 calls; element/material
and outside-Newton assembly totals were not independently available. These are
local instrumented diagnosis costs, not evidence of acceleration or AI benefit.
The two profile clocks above cover disjoint comparisons; they are not added to
the enclosing clocks.

The owned process exited zero and was reaped. Enclosing wrapper time was
195.518 s, child VmHWM 122,408,960 bytes and retained results 137,157,216 logical
bytes. The frozen limits were 900 seconds, 768 MiB output, 2 GiB live child
memory and 1,536 native calls. Source and original bytes stayed unchanged.
Logical file lengths and one process's VmHWM are not filesystem or hardware
qualification.

The original-file reviewer recomputed the response/mismatch predicates and
counters: 8,621 consistency checks, zero contradictions, and 2,367 inspected
original/proof files unchanged. This is internal original correspondence, not
an independent physical solver or laboratory comparison. A source-only final
review was written after launch; it is not retroactively a prelaunch receipt.

A separate read-only scalar experiment at the same source also found that
exact finite-input summation alone left the selected authored-B target-1
secant/proposal force comparisons outside the original criterion. It used no
material update, adapter solve or fit; it does not establish a unique cause for
all upstream response differences.

The host retains the full originals outside this repository in
`pr-backlog-20260929/full-training-numerical-followup-20261001/train-response-diagnosis-20261001/continuation-precision-20261001/fresh-path-precision-01/`.
The summary below does not imply these raw originals are distributed in a wheel
or published to GitHub.

| Immutable artifact | SHA256 |
| --- | --- |
| Frozen canonical numerical plan | `d7e23d1aa762d38401a5b07d68730fe5fea19bb241eb7eaad88e58d7519cef70` |
| Actual child outcome | `df5605e5cff7c634503089b92268b47c890df22180f200acf7bc7970c48cfe80` |
| Actual owned-process outcome | `bd6f2b9107ce4b0bcb17a8cc60d9d322522738dfe9d87404a291c9a8cdea8d31` |
| Original-file review | `71a4b9ce4c4c092c2124f51fa4f942efaadb727c2e2a1f450180a3c32d343667` |

The next learned-pair experiment needs explicit same-profile limit-2 generation,
teacher complements, original-file joins, inference and full-path cost evaluation.
Passing this TRAIN-only limit-1 diagnosis does not close that work, prove learned
gain, admit external data, or establish production readiness.


## Opt-in full-training profile and original export binding

The authored full-training driver can now prepare a new campaign with
`--arithmetic-profile retained-twofold-refinement.v1`. This existing learning
profile uses terminal refinement limit **2**. The fresh complete-path diagnosis
above used limit **1** and source `7cfc16fcab78b661f17bb6435fdecbe5db7127ed`;
its numerical outcomes do not verify the new limit-2 learning campaign.

The prepared plan freezes the exact arithmetic manifest and enables terminal
polishing in the typed request. Generation, complementary out-of-fold seed
headers, inference, teacher comparisons, join/fit and final path comparisons
forward the same profile. Rehashed changes to the authored roster, model,
request, solver settings or arithmetic manifest are rejected before solver
work. The default binary64 plan bodies for both original solver profiles and
all six model files remain byte-identical to the prior version except for the
driver artifact identity.

The original-generation exporter now checks the sample manifest, label
representation and retained low coordinates against the original plan,
runtime identity and accepted step. Two reproduced provenance gaps are closed:
adding retained metadata to ordinary binary64 originals and removing the
metadata from actual retained originals. The producer/consumer API is unchanged.
These are internal original-consistency checks; they do not establish an
independent producer or hardware attestation.

The final four source/test files passed **345 tests across five complete related
modules**, with zero failures, errors or skips. Ruff lint/format and whitespace
checks passed. Actual bytes of 8,923 guarded source paths were identical before
and after the final validation. The focused 104 tests are included in that
345-test total and must not be added again. Earlier intermediate runs are
preserved separately. The regression fixtures are software tests, not new
training observations or independent physical validation.

The raw final validation is retained under
`root-integration-whole-modules-02/receipt.json` in the continuation packet.
At that implementation checkpoint, the next numerical step was new limit-2
generation and labels at the published source, with the exclusion split and
matching non-AI baseline preserved. The E05 execution below completes that
specific experiment. Previous E04 labels and the limit-1 diagnostic remain
unchanged and are not admitted by metadata relabelling. The overall development
goal remains active.

## E05: completed limit-2 training and whole-path evaluation

The numerical source was **`cd74aa59ee57a5da3b835f1500e1009d7449b25b`**.
The frozen plan uses `extended-backtracking-v1`, terminal polishing and
`retained-twofold-refinement.v1` with refinement limit **2** in every arm.
These are six existing authored development cases: four TRAIN groups, one
validation case and one development holdout case. They are not independent
projects, newly unseen experimental specimens or a reserved locked cohort.
Validation and holdout outcomes did not select or refit the candidate.

| Completed stage | Observations / fits | Native calls | Newton / linear solves |
| --- | --- | ---: | ---: |
| Generation | 20 TRAIN samples; 1 fit | 73 | 654 |
| Excluded-group teachers and labels | 6 complementary fits; 60 pairs x 3 repeats | 741 | 5,775 |
| Original join and final pair | 20 verified rows; 1 seed fit and 1 gate fit | 0 | 0 |
| Whole-path evaluation | 6 cases x 3 repeats | 450 | 4,026 |
| Total | 9 fits; 180 label and 18 whole-path comparisons | 1,264 | 10,455 |

All four numerical stages exited zero and their owned children were reaped.
The original generation work agrees with the convenience result, with no
unknown work. All **18/18** final comparisons passed the existing internal
response/history criteria. Execution source descriptors for 962 public paths
were identical before, after and at the root's terminal check, with clean
source HEAD `cd74aa5`. This is correspondence to the same engine's fresh
reference runs; it is not independent physical validation.

The final training join has **20 verified negative rows, zero positive rows and
zero unknown/unavailable rows**. The pair was fitted and frozen before final
evaluation, but was not promoted. All final decisions abstained: 18 to the
reference initial value and 90 to secant, with **zero learned corrections**.

| Development split | Final comparisons | Mean conservative online time / secant |
| --- | ---: | ---: |
| TRAIN | 12 | 1.031121 |
| Validation | 3 | 1.031464 |
| Development holdout | 3 | 1.022761 |

The online ratio charges source setup, guard binding and the full proposal arm
to the candidate; offline generation, teacher and pair-fit costs remain
separate. These fixed-order observations show additional overhead, not AI
acceleration. No amortized benefit or generalization to independent projects
is established.

The enclosing owned wrapper took **812.683 seconds**; its nested supervisor
took 811.987 seconds. These clocks are not added together. Recorded output
inside the runtime/campaign scope was **664,888,890 logical bytes**. The largest
reported child VmHWM was the join stage's **1,219,502,080 bytes**; its separately
sampled live RSS maximum was 1,218,322,432 bytes. The declared caps were 1,800
seconds, 2 GiB output, 2 GiB live process memory, 2,048 native calls and nine
fits. These observations do not establish filesystem blocks/inodes, whole-host
memory capacity, independent hardware identity, or production response time.

The first external wrapper attempt found the pure-test symlink fixtures inside
its output-accounting directory and stopped before numerical stage entry. Its
supervisor exited -15 and was reaped; the original `unknown_work=true` receipt
is retained. A second runtime-only directory uses the exact same programs and
unchanged prepared inputs, with only four frozen path keys rebased. The actual
review and root byte guard preceded this successful first numerical campaign
execution. No completed campaign or numerical stage was restarted.

The full originals remain on the host under the continuation packet's
`e05-preparation-01/campaign/` and `e05-execution-02/`. Failure, review, validation
and follow-up records are under `e05-execution-01/`, `e05-recovery-review-02/`
and `e05-campaign-followup-20261001/`; they are not shipped in the wheel.

| Immutable artifact | SHA256 |
| --- | --- |
| E05 prepared numerical plan | `d6f0a08c57aa265c22a15153a5b7afb71473df48c57b7e6d08ca83246a76648e` |
| Successful owned wrapper outcome | `0b3192ea957b956697351ea521f17b7a78085ca1859af54ebd58fd0831aee34f` |
| Successful supervisor outcome | `61828ae59e24fce2a177cf07a40344e69f928523f92a4062b21bc69837c97ef5` |
| Root terminal source/owned-process guard | `fd767f5376e6acd8bb1c45f272dbed7998d6cfaa4da7c7f9f16fd5136022b154` |
| Preserved first failed wrapper | `1999cc7f195d5855163913aec9fe55178ca635e6c5f340f5dbff6ce1473c5468` |

### Browser readiness follow-up

The same-source hosted Workbench E2E failed while checking the eight unavailable
design deltas before the verified comparison panel was ready. The retained
trace subsequently contains the verified panel and all eight expected
`UNAVAILABLE` values. A focused test change explicitly waits for that panel
before the original count, value-state and no-selection assertions. No explicit
timeout values or expected results were changed.

The changed scenario passed once on desktop and once on mobile Chromium with
zero retries, using the verified Node 24.20.0 binary. Registration, TypeScript,
build and viewer delivery checks also passed. This scoped local validation does
not replace the complete hosted frontend or Python checks at the subsequent
published HEAD, and it is not a product performance improvement or release
approval. Independent experimental data, rights and operational dependencies
remain open.
