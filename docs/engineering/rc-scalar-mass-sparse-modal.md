# Exact scalar and positive diagonal mass sparse modal reduction

For exactly `M = c I`, solve the ordinary symmetric stiffness eigenproblem,
divide eigenvalues by `c`, and mass-normalize vectors by `sqrt(c)`. Reuse the
already computed largest algebraic stiffness eigenvalue for the generalized
spectral threshold. Mass factorization, positive-definiteness, stiffness
semidefiniteness, cluster, residual and orthogonality checks remain active.
For exact positive diagonal mass `M = D^2`, nonuniform entries (including a
one-ULP difference) use the symmetric problem `D^-1 K D^-1`. Eigenvectors
return to the original coordinates as `phi = D^-1 y` before residual and
mass-orthogonality checks. The transformed start vector corresponds to the
same original-coordinate start. Off-diagonal mass retains the generalized
path. No approximate scalar detection or shift-invert policy is introduced.
Buckling behavior is unchanged.

The regression includes a diagonal stiffness with one exact zero and two
repeated positive eigenvalues. The previous generalized extraction omitted
the exact zero and reported zero rigid modes; scalar reduction reports one.
This is a bounded regression, not a proof of arbitrary nullspace completeness.
The new nonuniform diagonal regression also reproduced the missing rigid
mode before the fix and reports one after the transformation. Arbitrary
nullspace completeness and non-diagonal singular problems remain unqualified. Output
schema is unchanged, but numerical values and artifact hashes may differ from
the previous extraction algorithm. Repeatability is checked within this version.

## Current diagonal-mass verification

The scalar, diagonal, generalized and canonical-memory solver tests passed
23 tests. The diagonal cases cover a rigid mode with repeated positive modes,
cluster truncation rejection, two nonuniform mass ranges compared to dense
solutions, original mass normalization, deterministic replay, invalid masses
and preservation of the non-diagonal generalized path. An additional 112-test
modal/buckling run passed 110 tests; two committed artifact checks rejected
stale source checksums already present at the committed HEAD. Regenerating
the four modal/buckling artifacts changed source hashes only, preserving
numerical results and claim boundaries; all 12 artifact tests then passed.
The core quality gate passed 156 tests, its 36-file typecheck and 86% branch
coverage against an 85% threshold. This gate has a bounded manifest scope and
does not by itself check the sparse solver. Focused Ruff checks, source
compilation, the frontend build/viewer delivery check, and all five contract
checks also passed. The optional Cursor CLI remains unavailable. The combined
full regression and exact new-HEAD hosted checks remain outstanding.

The isolated diagonal prototype measured before this production edit is stored
in `rc-diagonal-mass-prototype-20261012` on the secondary disk. Its source hash,
protocol and results bind that prototype, not the current production source.
The committed production measurement below is an independent campaign.

## Committed production cost measurement

Source `db0d3ca74bbb719387fca95c0c09bfa7e6e3c248`, solver SHA256
`dc02a0f96cc6d2baa803533c6e60db227b9810797dc6ada839b1b3976307bc31`,
was measured in 32 fresh processes / 64 solves. Four alternating dense/sparse
pairs per size and mass family passed identical analytic, small-chain,
shape, residual and orthogonality gates. All persisted hashes and exact
in-version two-solve replays were verified. Wall time includes startup,
imports, assembly, two solves, validation, serialization, persistence and exit.

| Mass | DOF | Dense median seconds | Sparse median seconds | Sparse faster pairs | RSS reduction |
| --- | --- | --- | --- | --- | --- |
| Uniform | 768 | 1.7768 | 1.8554 | 0/4 | 38.1% |
| Uniform | 1536 | 3.9194 | 3.6972 | 4/4 | 69.7% |
| Nonuniform | 768 | 1.7933 | 1.7861 | 2/4 | 38.0% |
| Nonuniform | 1536 | 3.9349 | 3.3298 | 4/4 | 69.7% |

The nonuniform 1536-DOF median is 15.4% lower; the 768-DOF timing difference
is inconsistent across pairs. Maximum small-chain relative error was
5.32e-11 and maximum analytic shape L2 error 1.17e-8. A combined full
regression ran concurrently on the same host. These four-pair observations
are bounded synthetic-family evidence, not a general speedup or physical RC
validation. Earlier prototype timings are historical, not simultaneous
controls. Protocol, script, individual results, hashes and report are in the
secondary-disk packet `rc-diagonal-mass-production-cost-20261012/`.

## Historical scalar verification and exploratory cost

The earlier scalar candidate passed 61 focused solver and workflow tests. Contract verification passed five
checks; the existing unavailable optional Cursor CLI warning remains.

A frozen grounded-chain protocol used 64, 256, 768 and 1536 DOF, three fresh
processes per backend/size, two solves per process, and one BLAS thread. Both
backends passed the same residual/orthogonality limits (1e-10), analytic
values, small chain contribution and shape checks, and exact in-version replay.
Timing includes process startup/import, assembly, conversions, two solves,
validation, serialization, persistence and exit. All 24 processes were accepted.

| DOF | Dense median seconds | Sparse median seconds | Dense / sparse peak RSS KiB (median) |
| --- | --- | --- | --- |
| 64 | 1.3748 | 1.3809 | 104444 / 103632 |
| 256 | 1.4047 | 1.4502 | 112228 / 103796 |
| 768 | 1.7560 | 1.8508 | 169852 / 105032 |
| 1536 | 3.8885 | 3.7514 | 354104 / 106884 |

At 1536 DOF the observed median wall time is about 3.5% lower and RSS about
69.8% lower. Only three repetitions were used; this is exploratory evidence
for this synthetic family, not a general speedup or product qualification.
The previous separate ungrounded 768-DOF residual failures remain failures;
grounding is part of this distinct predefined input, not a repair of that case.

The local packet is `artifacts/rc-scalar-modal-cost-20261009/` in the original
workspace. Its protocol records the parent commit; `candidate-source.sha256`
binds the uncommitted measured source and test bytes. Do not mistake that
parent SHA for the measured implementation. The subsequent commit must retain
those bytes. Historical reference measurements are not simultaneous controls.
No AI, GPU, physical specimen, general building or release claim follows.
