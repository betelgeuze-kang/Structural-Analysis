# Native ordinal history with an independent dead load

This explicit native profile retains every admitted source ordinal and binds one
immutable full plan, source checksum, raw-row checksums, declared channel mapping,
linear physical observation, independent global translational force pattern,
mechanical model, solver policy, initialization and whole-path budget. It does
not widen the existing public 255-target or subdivision limits. There is no new
public job, durable worker or UI admission in this change.

`HistoryRow` records `ordinal`, zero-based CSV logical `source_row`,
`source_row_sha256`, `target_m` and `axial_load_kn`. Source rows include header
records when compiled from a CSV; ordinals represent the retained numerical row
order, not measured seconds. The plan admits up to 65,536 rows. The caller must
explicitly admit a cumulative `maximum_solver_attempts` from 1 to 1,000,000.
The driver returns at most 255 events per entry; its cumulative reservation,
solver, commit, failure, assembly and hold-verification counts survive every
entry and strict continuation. No per-entry preload or prefix replay occurs.

The independent pattern has dimensionless signed UX/UY coefficients. A row's
`P` in kN adds `P*b` to the actual external vector, subtracts `S_f*P*b_f` from
the free residual, and enters support reactions and fixed step force/merit scales.
It is prescribed independently of the solved proportional factor lambda. Newton
uses a fixed scale including both parent and target P; terminal convergence,
commit, resume and holds also enforce the same canonical accepted-state scale
using base reference force and the current P. Large unloading therefore cannot
pass a looser completion gate and then fail solely because an entry ended. The
lambda column remains the full base assembled derivative, including member-load
features and lambda-prescribed support motion. The observer gradient is `c*S`;
its lambda derivative includes every prescribed-support term. Commit reassembles
the complete scheduled response before accepting material states.

Initialization is an explicit virgin zero constitutive projection followed by a
constrained first-record solve, even when that row's target and P are zero. It is
a declared reference initialization, not a reconstruction of a specimen's tare,
preload or material history. Unchanged authored `(g,P,support context)` rows
verify equilibrium/control and retain identical mechanical checkpoint bytes,
epoch and material states. They still advance the observation ledger. A changed
P with unchanged g performs a new constrained solve. Paired subdivision linearly
interpolates both g and P along the declared source segment; pending fractions
are canonical dyadic positions, so pure-P increments can progress.

The scheduled mechanical wrapper binds accepted P, exact nested lambda, the
last mechanical sample/fraction, prescribed target, ancestry and full context.
Observation ordinals are separate, so holds do not create artificial mechanical
epochs. The legacy v1 frame checkpoint remains a geometry/material projection;
it is not admitted alone as restart authority for this new scheduled profile.
The legacy API continues to accept its own valid v1 states under its old scope.

Canonical continuation bytes reject duplicates, unknown fields, nonfinite or
unsafe values, changed source/operator/pattern/config/budget, inconsistent nested
lambda/material hashes, skipped mechanical changes, malformed dyadic queues and
inconsistent cumulative cost/epoch bounds. Prefix solve/hold counts and permitted
mechanical ordinals are derived from authored change/hold runs, so a pending
mechanical solve cannot be smuggled onto an authored hold row. Redundant lambda
uses exact float64 equality, including signed zero; typed canonical byte
round-trip is required. Each execution entry separately reassembles
the accepted scheduled equilibrium before advancing; decoding performs no numerical
replay. Entry/verification work is also counted and bounded by the admitted attempt
budget plus the number of rows plus one. These are structural and corruption
checks. A self-rehashed native artifact does not authenticate a hostile prefix
or prove past cost. Trusted durable ledger custody or independently authorized
prefix verification remains necessary before exposing this profile publicly. Persistent crash custody, duplicate-worker
exclusion, managed backup, owner-controlled reservations and durable report/reopen
remain the I5 integration gap; the native codec does not complete them.

The 30,574-row test uses real native assembly and constrained solves for distinct
alternating displacement targets and changing P on an authored elastic member.
Its axial-force oracle, state custody and bounded return memory are software
verification. It does not reproduce CC3.3-10. The actual measurement reduction,
axial sign/load placement, initial state and complete cyclic steel/concrete laws
remain physical admission gates. Full actual CSV admission, numerical execution,
physical correspondence and fixed comparison are separate claims.
