# Exact scalar-mass sparse modal reduction

For exactly `M = c I`, solve the ordinary symmetric stiffness eigenproblem,
divide eigenvalues by `c`, and mass-normalize vectors by `sqrt(c)`. Reuse the
already computed largest algebraic stiffness eigenvalue for the generalized
spectral threshold. Mass factorization, positive-definiteness, stiffness
semidefiniteness, cluster, residual and orthogonality checks remain active.
Nonuniform mass, even a one-ULP diagonal difference, and off-diagonal mass
retain the generalized path. No approximate scalar detection or shift-invert
policy is introduced. Buckling behavior is unchanged.

The regression includes a diagonal stiffness with one exact zero and two
repeated positive eigenvalues. The previous generalized extraction omitted
the exact zero and reported zero rigid modes; scalar reduction reports one.
This is a bounded regression, not a proof of arbitrary nullspace completeness.
Non-scalar singular problems have not been qualified by this change. Output
schema is unchanged, but numerical values and artifact hashes may differ from
the previous extraction algorithm. Repeatability is checked within this version.

## Verification and exploratory cost

61 focused solver and workflow tests passed. Contract verification passed five
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
