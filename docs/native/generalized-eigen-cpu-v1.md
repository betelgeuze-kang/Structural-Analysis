# Bounded native generalized-eigen CPU v1

Status: C0 and C1 complete; ABI v1.9/Rust C3 implementation complete, sequential promotion C1

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
- C2 candidate: a product-owned bounded HIP cyclic-Jacobi kernel keeps the eigensolve,
  canonicalization and result recovery resident and has source-bound local live CPU/HIP parity,
  bitwise repeats and fallback zero. Its execution profile is explicitly a single-thread dense
  reference, not a scalable sparse eigensolver. Authoritative C2 remains open until the protected
  `native-hip-approved` runner emits the approved source/device receipt.
- C3 implementation: ABI v1.9 consumes the two former 144-byte table reserved slots for distinct
  modal and buckling operations. It validates versioned dense inputs, packed host FP64 views,
  dimensions, pointer extents, descriptor/data overlap and disjoint caller-owned outputs. Both
  operations stage every channel and result before publishing, map the fixed solver taxonomy,
  contain C++ exceptions, expose fallback zero, and remain immutable/reentrant. The checked Rust
  mirror fixes every layout/offset, and its safe wrapper validates dimensions and complete output
  invariants before constructing owned mode objects. C++ ABI contracts, an ABI libFuzzer harness,
  Rust layout tests, safe parity/taxonomy tests, concurrent bitwise-repeat tests and installed C11
  package consumption cover this integration. Because protected-runner C2 remains open, this
  implementation does not advance the sequential capability beyond C1.
- C4 bounded CPU implementation: a canonical SAEIGC01 artifact binds the exact strict request,
  model, validated-ready state, execution configuration and aggregate checkpoint identities. The
  native solve is atomic, so this is an honest pre-dispatch phase boundary rather than an
  invented mid-Jacobi state. Every byte mutation and request drift fails closed.
- C5 bounded CPU implementation: public eigen-run/eigen-resume commands emit canonical
  self-hashed ResultIR/ReportIR, deterministic Markdown, the phase checkpoint and an atomic
  receipt. Modal and buckling direct/resume directories are byte-identical with Python/Node
  lookup removed. This separately tracked product capability does not bypass the open protected
  C2 gate or broaden the C1 numerical scope.
- C6: open. Python remains the oracle and rollback authority; nothing is decommissioned.

The current sequential promotion is therefore C1 only; the local HIP work and v1.9/Rust work are
retained as C2/C3 implementation candidates behind the protected-runner C2 gate. The exact
C4/C5 product contract and remaining boundaries are documented in
docs/native/generalized-eigen-product-e2e-v1.md.
