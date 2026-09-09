# Experimental RC control warm-start boundary and runtime comparison

The internal displacement-control step accepts an optional copied vector of
original augmented Newton coordinates: free generalized coordinates followed by
`load_factor_coordinate_scale_m * lambda`. It changes only the initial iterate.
Every trial still uses the same original parent, fixed-chord assembler and
material laws. The original residual, increment, control, parent/source and
solver/assembly binding gates decide commit; failure retains exact rollback.
There is no hidden retry inside the step. An explicit seed and its hash are
recorded only when supplied, preserving default step and API artifact bytes.

`benchmark_rc_control_seed_paths` runs reference, deterministic secant and an
optional caller-proposal arm independently from epoch zero. A proposer receives
only that arm's already accepted target/coordinate prefix; it is never passed the
reference history or future target labels. The caller declares a proposal hash;
that declaration does not authenticate its implementation or training data. The
benchmark performs no training and does not prove project/geometry/history split
independence. Existing public load-control learned policies cannot be relabeled
as trained cyclic-control policies.

Each accepted transition is reassembled from the original Newton coordinates
against its original parent. The recovered checkpoint and complete assembly
must match exactly, and equilibrium/control are checked again. All node,
reaction, member, section and fiber/material history values are retained. After
all arms, a fresh complete reference path runs from epoch zero. Reference repeat
bytes must match exactly. Cross-arm physical values use declared absolute and
relative tolerances; their state hashes need not match across different Newton
trajectories. The original profile's tolerance defaults remain `1e-10` absolute
and `1e-8` relative; failures are retained rather than changing those thresholds.

Before proposing or solving, started records are written to a new exclusive
output directory. A malformed/raised proposal falls back to the parent start.
A returned noncommitting seeded solve may fall back once only after exact
rollback; both entries and their costs are recorded. A numerical exception
stops that arm with unknown work and no retry. Existing Newton failure results
sometimes omit iteration/linear counts: those stay null/unknown even when an
exact-rollback fallback can proceed. Known core entries are distinct from
unknown inner solver work. Wall/CPU measurements include proposal generation,
all attempts, recovery and output I/O; whole-study time additionally includes
validation, compilation and comparison, excluding final report hashing/writing.

The requested strategy order is explicit so repeated fresh-process observations
can alternate order. A surviving complete path does not erase failed attempts,
missing work, reference mismatches or an incomplete alternative. Local timing
and response equivalence are not independent physical validation, a public
API expansion, a learned-policy generalization result or design/release approval.
The canonical API, CLI, durable-job and Workbench schemas do not accept seeds.

Focused tests cover invalid vectors before Newton, immutable caller snapshots,
real seeded/reference gates, rollback without hidden core retry, forged increment
success, unchanged original API/checkpoint bytes, complete independent paths,
rejected-proposal fallback, actual noncommitting seeded fallback with unknown
counts, and exceptions without retry. Initial development checks exposed a
benchmark counter-key mismatch and absent counters on a returned blocked solve;
the original failed records are retained as wrapper/cost-accounting failures.

The frozen development observation ran over the complete existing 242-target
path for the authored 2.0 m/1.5 m L-frame and a separate 2.5 m/2.0 m geometry, three
fresh processes each. The request, materials and tolerances are fixed in advance;
reference/secant order alternates across the six workers. These are local authored
geometry variants, not independent projects or a held-out licensed corpus. Learned
cyclic data collection/training and broader independent acceptance remain open.


## Frozen 242-target repeated observation

Source `707702f8825def701cf4a36cbdea57b747353770` was copied into an
isolated 408-file Python tree and checked unchanged after all workers exited.
Six predeclared serial fresh processes alternated reference/secant order; each
also ran a fresh reference. All 18 paths completed all 242 targets, with no retry,
failed attempt or unknown work: 4,356 core entries and 14,757 Newton iterations /
linear solves. Parent elapsed time was 653.659 seconds. Reference and secant
histories each reproduce exactly across their geometry's three processes, and
all six reference/fresh-reference pairs are byte-exact. This establishes local
repeatability, not independent validation.

| Geometry (m) | Reference median ± sample SD (s) | Secant median ± sample SD (s) | Newton counts reference / secant | Secant full-history pass |
| --- | --- | --- | --- | --- |
| 2.0 / 1.5 | 39.139 ± 0.415 | 27.997 ± 0.135 | 960 / 582 | 0 / 3 |
| 2.5 / 2.0 | 37.454 ± 0.116 | 27.120 ± 0.248 | 934 / 549 | 0 / 3 |

These path times include original transition recovery and step I/O; whole-study
cost additionally includes the fresh reference, compilation and comparison.
Despite shorter times and fewer iterations, **no performance improvement is
accepted**: all six secant paths fail the predeclared full-history comparison.
The original `1e-10` absolute / `1e-8` relative tolerances remain unchanged.

A saved-data audit identifies 2,115 out-of-tolerance numeric leaves per base
repeat and 2,057 per longer-geometry repeat. They occur in member end forces,
support reactions and section results. Displacement, load-factor and fiber
history leaves pass these comparisons; this does not cancel the failed force
comparisons. The first failing base value is at target index 1, member 0 local
end-i `FX_N`: reference `-1.4210854715202004e-11` N versus secant
`-3.5558223032694514e-08` N. The largest failing base absolute difference is
`1.4829396377535886e-05` N at index 128 in that axial-force field; longer geometry
has `1.290706563850108e-05` N at index 135. Small near-zero force differences can
exceed the strict absolute threshold even when each solver's own normalized
residual/increment gates pass. A larger mixed-field absolute difference in the
original summary can itself pass its relative allowance; it is not the largest
*failing* value. No mismatch is removed or relabeled as a passing comparison.

A second saved-data audit checks all 4,356 original started/outcome/step records,
report/path hashes, own-prefix proposal contexts, unchanged parent chains,
original residual/increment/equilibrium/control/assembly gates, and exact reported
iteration/linear counts. Neither audit calls the solver. Raw source, inputs,
original failures, all six workers and both audit scripts are retained in the
[observation summary](rc-control-seed-runtime-20260909.summary.json).

## Browser CI follow-up and validation

At preceding published head `715dc9876`, the frontend lane finished with 468
passes and five failures; frontend-contracts finished with 467 passes and six
failures. Retained output identifies RC study loading assertions with 5-second
deadlines; the first frontend-contracts error header is absent from its truncated
200-line tail. This is not a final-head CI success claim.

The RC browser tests now wait at the original-artifact validation boundary for
a settled `verified` or `invalid` state, then assert the exact required outcome.
Only this wait has a 60-second upper bound; the existing whole-test deadline,
application worker timeout, numerical checks, download hashes and rendering
assertions are unchanged. Two regression cases delay a required original result
by six seconds: valid bytes become verified, while tampered bytes remain invalid
with no candidates. Full local frontend verification passes **475 tests in 1.4
minutes**, including TypeScript checking, build and viewer-delivery validation.

Python validation passed 214 focused/core/API/registration tests after preserving
and fixing two wrapper accounting failures. A later preflight-only addition
passed its 19-test focused group. These overlap; they are not a full-repository
Python suite. Ruff and diff checks passed. The public API default result and
checkpoint retain exact original fixture bytes.

The next numerical acceptance work is to investigate shared convergence finishing
for every compared strategy without changing the comparison thresholds or
replacing this failed observation. Learned cyclic-control sample generation,
train-only fitting and independent split validation remain open. Current-main,
separate R2, licensing, hardware and owner-dependent gates remain separately open.
