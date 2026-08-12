# Bounded native generalized-eigen CPU v1

This slice transfers one strict numerical family to `structural_solver_cpu`: bounded dense,
symmetric modal analysis (`K phi = omega^2 M phi`) and linear buckling
(`K phi = lambda Kg phi`). It is a reference product kernel, not a claim of general sparse
eigensolver authority.

## Contract

- Matrices are caller-owned row-major FP64 arrays with order 1 through 128.
- Modal analysis requires positive-definite mass and positive-semidefinite stiffness.
- Buckling requires positive-definite elastic stiffness and positive-semidefinite geometric
  stiffness; rank-deficient geometric stiffness is allowed and its infinite modes are filtered.
- Symmetry, dimensions, finite values, recovery scales and tolerances fail closed.
- A deterministic serial cyclic-Jacobi decomposition, fixed stable ordering, complete-cluster
  selection and coordinate-axis eigenspace canonicalization remove sign/basis ambiguity.
- Modal modes are mass normalized; buckling modes are elastic-stiffness normalized.
- Residual, orthogonality and diagonalization gates publish no partial modes on failure.
- Regularization and fallback do not exist; `fallback_count` is always zero.

## Evidence and cutover boundary

- C0: C++20 unit tests cover closed forms, rigid and infinite modes, scaling recovery,
  repeated-mode canonicalization, malformed/indefinite matrices, cluster cuts, deterministic
  repeat, nonconvergence taxonomy and failure atomicity. A bounded libFuzzer harness covers both
  operations.
- C1: six versioned-in-source profiles match an independent SciPy `eigh` oracle for eigenvalues,
  physical normalized modes, residuals, ranks and fallback count.
- C2: open. No modal or buckling HIP kernel, resident subspace buffer, deterministic GPU
  reduction or approved hardware receipt is claimed.
- C3: open. The operation is not yet appended to `sa_get_api_v1` and has no Rust safe wrapper.
- C4: open. Eigen execution/checkpoint identity and restart are not implemented.
- C5: open. No public CLI/API/Workbench ResultIR/ReportIR path consumes this solver yet.
- C6: open. Python remains the oracle and rollback authority; nothing is decommissioned.

The current sequential promotion is therefore C1 only.
