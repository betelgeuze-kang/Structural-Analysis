# Engine v2 CPU FGMRES Fixed-Rank Coarse Preconditioner v1

Status: v0.2.55 local implementation candidate
Scope: deterministic CPU diagnostic contract for `ExecutionPlanV2`
Promotion: non-promoting CPU reference; HIP/AMG/DD/product claims remain open

## Purpose

This increment connects a bounded orthogonal coarse space to the actual
fixed-restart FGMRES right-preconditioner path. It closes the gap between the
earlier AI projection scaffold and an iterative solver consumer without changing
the existing Jacobi-only CPU reference result schema or any HIP recurrence ABI.

The candidate vectors may come from physics modes, accepted Krylov history, or an
AI proposal. Their origin does not grant numerical authority. The sparse physical
operator remains the truth, and the final FGMRES result is accepted only through
the existing full true-residual gates.

## Numerical contract

For reduced sparse stiffness `A`, positive diagonal `d = diag(A)`, and physical
candidate modes `U`, the compiler forms square-root-energy coordinates

```text
D = diag(d)^(-1/2)
X = D^(-1) U
Q = two_pass_mgs(X),  Q^T Q ~= I,  rank(Q) = k <= 16
Z = D Q
AZ = A Z
E = Z^T A Z = L L^T
```

`E` must be finite, symmetric positive definite, and below the configured
condition limit. A zero/dependent-only basis, a non-positive Jacobi diagonal, or a
failed Cholesky factorization is rejected before solver execution.

One right-preconditioner application uses the retained `AZ` columns:

```text
c   = E^(-1) Z^T r
z_c = Z c
z   = z_c + diag(A)^(-1) (r - AZ c)
```

No additional CSR application occurs inside the preconditioner. For every
retained coarse mode, the construction gives `M^(-1)(A z_c) ~= z_c` to FP64
roundoff. The ordinary FGMRES operator application, Arnoldi recurrence, Givens
updates, and full true-residual replay remain unchanged.

## Storage and complexity boundary

The artifact retains:

- one `N`-entry inverse square-root diagonal,
- at most `k <= 16` candidate, scaled-basis, physical-basis, and `AZ` columns,
- only two `k x k` dense arrays: the coarse operator and its Cholesky factor.

It never constructs or stores `Q Q^T`, `Z Z^T`, or any other `N x N` dense
projector.

| Operation | Contracted work | Boundary |
| --- | ---: | --- |
| basis build | `O(N k^2)` | fixed `k <= 16` |
| `AZ` build | `O(nnz k)` | sparse CSR only |
| small factorization | `O(k^3)` | maximum dense dimension `k` |
| one application | `O(N k + k^2)` | retained `AZ`, no extra CSR matvec |
| storage | `O(N k + k^2)` | source plan storage excluded |

This bounded local work is not proof that the complete solver is `O(N)`. A valid
near-linear product claim still requires a real multilevel hierarchy and measured
mesh-independent iteration/operator-complexity scaling.

## Receipts and validation

The coarse-space artifact is bound to the exact retained `ExecutionPlanV2` and
replays:

- plan/operator/numeric/symbolic/partition hashes,
- CSR Jacobi diagonal and energy scaling,
- candidate bytes and deterministic two-pass MGS,
- scaled orthogonality errors,
- all `AZ` columns and the symmetric coarse operator,
- eigenvalue condition estimate and Cholesky factor,
- exact vector-kernel, CSR-build, storage, and per-application counts,
- immutable little-endian FP64 storage and descriptor hashes.

The result contract independently replays the sparse true residual, FGMRES
history/count/status invariants, effective coarse-plus-Jacobi policy, aggregate
coarse work, result arrays, canonical hash, and a deterministic full solve.

The source `FgmresPolicyV1` still describes the legacy recurrence controls. The
new result serializes it as a source policy and separately names the effective
preconditioner, avoiding a false claim that the coarse run used Jacobi alone.

## Current verification

- fixed-rank numerical/adversarial/public/schema focused set: `21 passed in 7.53s`
- focused plus existing CPU FGMRES reference/checkpoint-history regression:
  `52 passed in 120.60s`, wall `121.19s`, peak RSS `132,432 KiB`
- existing AI projection/solver-approved QR memory plus the new coarse path:
  `49 passed in 14.90s`
- frame weak-axis teacher case: Jacobi reference `2` iterations, fixed-rank coarse
  result `1` iteration, same sparse-direct displacement within FP64 tolerance
- exact coarse-mode application error in the focused probe:
  max absolute `1.3010426069826053e-18`
- public symbols after the concurrent reviewer-root v3 increment and this additive
  contract: Engine/Assembly/Solvers `1152/960/66`
- current dirty-tree wheel smoke: `316` members; the coarse solver module and both
  schemas are present, and an isolated install passes Engine/Solvers public
  identity with `1152/66` symbols

The wheel smoke is packaging-only and is not a reproducible or authoritative
release artifact. These numbers are local CPU diagnostics, not a benchmark or
speedup claim.

## Explicit exclusions

This increment does not establish:

- HIP/ROCm execution or device-resident coarse application,
- AMG levels, smoothers, interpolation, domain decomposition, RAS, or GENEO,
- mesh-independent Krylov iteration counts or measured complexity slope,
- nonlinear tangent, shell, solid, contact, dynamic, or multi-RHS coverage,
- iteration-wide host-copy-zero, multi-GPU, or distributed halo behavior,
- signed/persistent promotion evidence,
- ResultIR authority, code-check authority, or commercial readiness.

## Next integration steps

1. Port the exact `Z`, `AZ`, small-factor, and application ABI to HIP with a
   device-resident fixed-rank kernel and zero iteration D2H.
2. Replace caller-supplied global modes with partition/interface modes from an
   actual first DD hierarchy.
3. Add one-level smoother and coarse-grid composition receipts, then extend to
   multilevel AMG/DD with bounded operator complexity.
4. Measure iteration growth, operator complexity, wall time, and memory across a
   mesh family before making any near-`O(N)` statement.
5. Admit T-GNN/E(3)-GNN/PINN modes only as bounded candidates; keep the same sparse
   physics replay and rollback gates.
