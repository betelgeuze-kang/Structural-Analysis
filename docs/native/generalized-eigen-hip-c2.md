# Bounded generalized-eigen HIP C2

Status: product-owned implementation and live local C2 candidate complete; protected-runner
promotion pending.

## Product-owned bounded backend

`structural_solver_hip` now owns a no-fallback FP64 backend for the same at-most-128-DOF dense
modal and linear-buckling contract as the CPU C1 reference. The host rejects invalid dimensions,
non-finite values, asymmetric matrices, invalid recovery scales and invalid tolerances before
launch. It projects accepted matrices symmetrically but does not perform a spectral solve.

One product HIP kernel performs both physical source spectra, congruence scaling, Cholesky
generalized-eigen transformation, cyclic-Jacobi sweeps, rigid/infinite-mode filtering, complete
cluster selection, coordinate-axis canonicalization, physical shape recovery, residual checks and
Gram gates. Matrices, eigenvectors, iteration decisions and recovery scratch remain on the selected
device. Each call performs exactly three H2D transfers, one final packed D2H transfer, one kernel
launch and one final synchronization. There is no CPU dispatch and `fallback_count=0` is invariant.

The execution profile is deliberately named `single_thread_cyclic_jacobi_fp64.v1`. It is a
deterministic bounded single-thread reference kernel, not a claim of scalable sparse eigensolver
performance. FP contraction is disabled and every reduction/rotation order is fixed. A later
sparse/subspace backend must earn its own performance and parity receipts rather than inheriting
this claim.

## Live parity and receipt

The dedicated executable compares four modal and four buckling profiles against the C++ CPU C1
source. Coverage includes non-identity coordinate recovery, rigid and infinite modes, repeated
eigenspaces, singular geometric stiffness and a `1e-15` reciprocal mode. Every successful profile
runs twice and must be bitwise identical. Numerical nonconvergence and residual-limit executions
must preserve the shared status without partial modes, while eight definiteness,
mode-availability and cluster-cut profiles must fail with the same CPU/HIP contract category.

The source-bound receipt records device, runtime, driver, compiler and compiled architecture;
header/source and OCML/OCKL/ISA SHA-256; maximum eigenvalue, shape and result-metric parity errors;
H2D/D2H bytes and counts; synchronization, launch, resident-buffer and visible-VRAM counters; and
explicit device-resident eigensolve/result-recovery, zero host intermediate/control transfer and
zero fallback declarations.

Local RX 6900 XT (`gfx1030`) execution on ROCm 6.0.2 completed 18/18 receipted executions with
bitwise repeats, CPU/HIP numerical-status and contract-failure parity, maximum relative eigenvalue
error `1.3706125276112035e-16`, maximum shape error `5.5511151231257827e-17`, maximum result-metric
error `4.4408920985006262e-16`, and fallback zero. This is only a C2 candidate. Authoritative C2
requires the same source SHA from `.github/workflows/native-hip-dedicated.yml` in the protected
`native-hip-approved` self-hosted environment.

## Remaining boundary

This candidate does not implement sparse extraction, Lanczos/subspace iteration, whole-model
modal/buckling assembly or Python/Node decommission C6. Separate bounded CPU implementations now
provide the honest pre-dispatch C4 phase checkpoint and C5 eigen-run/eigen-resume product path;
the HIP candidate neither proves nor inherits those gates. ABI v1.9 and its Rust wrapper remain
C3 implementation evidence, but sequential numerical capability promotion stays C1 until the
protected C2 receipt is available.
