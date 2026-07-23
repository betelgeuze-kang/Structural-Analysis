# Sparse Factorization and Conditioning Diagnostics

The public corotational sparse path uses unregularized SciPy SuperLU factorization with
`COLAMD` ordering. It never substitutes a dense solve, regularized matrix, least-squares
answer, or fallback result when factorization or a diagnostic gate fails.

`public_sparse_factorization_fail_closed.v1` requires, for the current bounded profile:

- exact matrix 1-norm condition number no greater than `1e12`, computed by sparse LU
  solves of individual basis columns without materializing the global tangent as dense;
- minimum normalized absolute U pivot at least `1e-14`;
- normwise backward error no greater than `1e-12`;
- at most 256 equations for this exact conditioning procedure;
- finite factors and solution, with no regularization or fallback.

Each factorization emits a schema-validated canonical receipt binding the CSR pattern and
values, right-hand side, solution, row/column permutations, L/U nonzero counts, fill
ratio, pivot extrema, condition number, backward error, policy hash, and individual gate
outcomes. A policy failure raises `SparseFactorizationError`; a blocked diagnostic is
retained when factorization succeeded but quality was unacceptable.

These thresholds are a bounded public-candidate policy, not proof for arbitrary model
sizes.

## Larger bounded experimental diagnostic

`experimental_blocked_exact_sparse_factorization_fail_closed.v1` provides a separate
CPU-only research path for at most 1536 equations. It keeps the same unregularized
SuperLU/COLAMD and fail-closed quality gates, but computes the exact inverse matrix
1-norm by solving canonical identity columns in deterministic blocks of 32. Its receipt
additionally binds the block size/count and fixes the following claims to false:

- production-scale sparse policy;
- external V&V; and
- release authority.

Its nonlinear-3D integration claim is false in this PR. A later bounded 3D graph
integration must add a real solve-level receipt before changing that claim.

The detached validator rechecks the policy hash, equation and block limits, fill-ratio
relationship, required invariant checks, numerical policy relationships, and the exact
status/failure-code mapping even after a caller recomputes the outer receipt hash. A
257-equation non-diagonal reference and a 300-equation deterministic case pass; singular,
out-of-scope, ill-conditioned and relationship-tampered cases fail closed.

This remains a standalone quadratic-work exact diagnostic and is not wired into the
public corotational API or a nonlinear 3D backend. A production-scale path still requires
a separately reviewed scalable estimator/policy, representative performance and memory
receipts, and external validation.
Passing either receipt does not create engineering, design-code, Level 2, or release
authority.
