# Bounded Sparse Linear CPU v1

Status: C0 and C1 complete; live local HIP C2 candidate, ABI/Rust C3, CPU checkpoint C4 and
public product C5 implementation complete. Sequential numerical promotion remains at C1 until
the protected-runner C2 receipt closes.

## Native owner

`structural_solver_cpu` owns a serial FP64 canonical-CSR matrix view, deterministic matrix-vector
product and Jacobi-preconditioned conjugate-gradient solve. Input validation rejects zero or
oversized dimensions, inconsistent row offsets, out-of-range or duplicate/unsorted columns,
non-finite coefficients, asymmetric structure and asymmetric values before numerical execution.
The PCG path requires a positive diagonal, performs a true-residual postcheck before convergence
is published, and has no fallback branch.

The stable solver taxonomy reserves distinct values for invalid input, singularity, indefinite
operator, nonconvergence, increment limit, residual limit, cancellation, checkpoint mismatch and
backend unavailability. This slice exercises singularity, indefinite operator, nonconvergence and
failure-atomic increment rejection. ABI v1.8 maps each one-shot outcome to a fixed status code
without publishing a partial solution or result structure. ABI v1.10 appends begin/advance
operations over a complete caller-owned state while preserving all v1.0-v1.9 table prefixes.

## Evidence

C0 consists of the C++ unit matrix:

- a five-DOF SPD solve and bitwise repeat;
- zero RHS and exact-initial-guess zero-iteration exits;
- malformed offsets, non-finite values, unsorted/duplicate columns and both forms of asymmetric
  CSR rejection;
- singular, indefinite, nonconverged and increment-limit outcomes with fallback zero.

A bounded libFuzzer target mutates valid diagonally dominant SPD systems into malformed offsets,
duplicate columns, non-finite coefficients and asymmetric operators under ASan/UBSan.
An additional ABI fuzzer mutates nested view lengths, strides, overlap, reserved fields and
numerical config at the exception-containing C boundary.

C1 compiles the product source independently and compares four profiles (`spd5`, irregular
20-nonzero `irregular6`, condition-scaled diagonal `scaled4`, and `zero5`) with NumPy
`linalg.solve`. Every solution and recomputed residual is compared, while positive definiteness
and profile coverage are independently checked with NumPy eigenvalues.

## Later implementation gates without sequential promotion

- C2 candidate: the source-bound fixed-tree FP64 HIP execution is locally live with resident PCG
  state, bitwise repeats, exact status/iteration parity and fallback zero. Promotion still requires
  the protected ROCm receipt described in `sparse-linear-hip-c2.md`.
- C3 implementation: ABI v1.8 provides the one-shot operation and ABI v1.10 adds failure-atomic
  begin/advance calls. Both validate caller-owned packed U64/U32/F64 views, all four mutable state
  buffers, pointer extent, overlap and overflow, and cross a safe reentrant Rust wrapper. C3 is
  not sequentially promotable until authoritative C2 evidence exists.
- C4 implementation: the pointer-free `SAPCGC01` artifact serializes the exact real PCG iteration
  state and binds strict request, model, state, execution and aggregate checkpoint SHA-256
  identities. Every byte mutation and request/configuration drift fails closed with code 1301.
- C5 implementation: public `linear-run` and `linear-resume` commands execute by an explicit real
  iteration budget and publish a checkpoint receipt at active, converged or numerical-terminal
  boundaries. Converged runs additionally publish self-hashed ResultIR, ReportIR and deterministic
  Markdown. Direct and resumed terminal artifact directories are byte-identical with the process
  environment cleared and Python/Node lookup unavailable.

See `sparse-linear-product-e2e-v1.md` for the exact C4/C5 boundary. These two bounded CPU
implementation capabilities do not bypass the missing protected C2 receipt.

## Remaining authority

- C6: convert the independent NumPy oracle into reviewed language-neutral golden data, preserve a
  rollback/deprecation window, and remove the corresponding Python test authority only after the
  sequential C2/C3 acceptance and packaging evidence exists.
- ModelIR-derived arbitrary sparse assembly, durable queued jobs/API, PDF projection, engineering
  acceptance and HIP-backed product execution remain open.

This reference family is not general constraint elimination, ordering, sparse direct
factorization, indefinite solving, multigrid/preconditioner coverage, Newton, modal, buckling or
transient analysis.
