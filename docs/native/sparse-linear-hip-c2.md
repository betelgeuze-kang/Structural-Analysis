# Bounded Sparse Linear HIP C2

Status: product-owned implementation and live local C2 candidate complete; protected-runner
promotion pending.

## Product-owned execution context

`structural_solver_hip` is compiled only with `STRUCTURAL_ENABLE_HIP=ON`. Before allocation it
calls the same C++ `validate_sparse_spd_problem` source as the CPU reference, so canonical CSR,
symmetry, finite-value, vector-length and convergence rules cannot drift. Its current bounded
domain is 65,536 equations, 4,000,000 nonzeros and 10,000 iterations.

One HIP block owns the complete Jacobi-PCG execution. CSR values, row/column indices, RHS,
solution, residual, preconditioner, search direction, operator direction, candidate and scalar
iteration state stay in device memory for the entire solve. FP64 dot products and norms use a
fixed 256-thread binary reduction tree with contraction disabled. The host performs no scalar
poll, convergence decision, synchronization or intermediate-vector transfer per iteration.
Numerical errors return the shared singularity, indefinite-operator, nonconvergence,
increment-limit and residual-limit taxonomy. A HIP failure throws and there is no CPU dispatch;
`fallback_count=0` is invariant.

## Live parity and receipt

The dedicated executable compares `spd5`, irregular 20-nonzero `irregular6`, `scaled4` with a
`4e12` diagonal condition ratio, and `zero5` against the CPU C1 source. Each successful profile
runs twice and must be bitwise deterministic; an exact nonzero initial guess must exit in zero
iterations. Four additional executions require exact CPU/HIP status and iteration parity for
singularity, indefinite operator, nonconvergence and increment limit.

The source-bound receipt records:

- selected device id/name, runtime architecture, ROCm runtime/driver and compiler;
- compiled architecture plus SHA-256 of the HIP header/source and OCML/OCKL/ISA bitcode;
- maximum solution, recomputed true-residual and solver-metric errors;
- H2D/D2H bytes and transfer counts, synchronization count, kernel launches and peak resident
  bytes against visible VRAM;
- FP64/fixed-tree determinism, device-resident iterations, zero host intermediate/control
  transfers and zero fallback.

Local RX 6900 XT (`gfx1030`) execution on ROCm 6.0.2 produced 13/13 passing solves, bitwise
repeats, exact status/iteration parity, maximum solution error `4.4408920985006262e-16`, maximum
true-residual error `3.5527136788005009e-15`, and fallback zero. This remains a C2 candidate:
authoritative promotion requires the same source SHA in the manual `native-hip-dedicated`
workflow on the protected `native-hip-approved` self-hosted runner.

## Remaining boundary

This does not yet promote the append-only ABI/Rust C3 implementation, persist complete PCG state
for checkpoint C4, connect ModelIR/job/ResultIR/ReportIR C5, implement multi-block and vendor
sparse preconditioners, general Krylov/Newton/eigen/transient execution, or close C6. The
capability manifest therefore remains sequentially at C1 until the protected C2 receipt exists.
