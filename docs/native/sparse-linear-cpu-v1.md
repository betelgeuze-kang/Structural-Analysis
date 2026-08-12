# Bounded Sparse Linear CPU v1

Status: C0 and C1 complete for one canonical-CSR SPD/PCG reference family.

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
failure-atomic increment rejection; ABI error mapping is deliberately deferred to C3.

## Evidence

C0 consists of the C++ unit matrix:

- a five-DOF SPD solve and bitwise repeat;
- zero RHS and exact-initial-guess zero-iteration exits;
- malformed offsets, non-finite values, unsorted/duplicate columns and both forms of asymmetric
  CSR rejection;
- singular, indefinite, nonconverged and increment-limit outcomes with fallback zero.

A bounded libFuzzer target mutates valid diagonally dominant SPD systems into malformed offsets,
duplicate columns, non-finite coefficients and asymmetric operators under ASan/UBSan.

C1 compiles the product source independently and compares four profiles (`spd5`, irregular
20-nonzero `irregular6`, condition-scaled diagonal `scaled4`, and `zero5`) with NumPy
`linalg.solve`. Every solution and recomputed residual is compared, while positive definiteness
and profile coverage are independently checked with NumPy eigenvalues.

## Remaining sequential gates

- C2: implement and execute source-bound CPU/HIP sparse parity on the protected ROCm lane.
- C3: publish caller-owned CSR/vector descriptors through append-only `sa_get_api_v1` and a safe
  Rust wrapper.
- C4: bind complete iterative state and model/state/execution hashes into checkpoint/restart.
- C5: run a ModelIR-derived sparse problem through CLI/job/API to ResultIR and ReportIR.
- C6: convert the oracle to language-neutral golden data and remove the corresponding production
  and test Python authority after rollback/deprecation evidence exists.

This reference family is not general constraint elimination, ordering, sparse direct
factorization, indefinite solving, multigrid/preconditioner coverage, Newton, modal, buckling or
transient analysis.
