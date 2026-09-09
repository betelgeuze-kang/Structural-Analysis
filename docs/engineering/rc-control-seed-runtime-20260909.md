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

A frozen development observation is planned over the complete existing 242-target
path for the authored 2.0 m/1.5 m L-frame and a separate 2.5 m/2.0 m geometry, three
fresh processes each. The request, materials and tolerances are fixed in advance;
reference/secant order alternates across the six workers. These are local authored
geometry variants, not independent projects or a held-out licensed corpus. Learned
cyclic data collection/training and broader independent acceptance remain open.
