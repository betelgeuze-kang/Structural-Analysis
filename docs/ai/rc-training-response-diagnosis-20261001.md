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
