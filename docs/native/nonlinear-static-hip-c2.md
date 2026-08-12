# Bounded Nonlinear-Static HIP C2

Status: product-owned implementation and live local C2 candidate complete; protected-runner
promotion pending.

## Product-owned execution context

`structural_solver_hip` is compiled only with `STRUCTURAL_ENABLE_HIP=ON`. Before device
allocation it calls the same C++ `validate_nonlinear_static_problem` source as the CPU reference,
so story shape, finite values, positive stiffness/height and Newton-control domains cannot drift.
The current device profile is bounded to 256 stories and 10,000 Newton iterations.

One HIP work item owns the full deterministic reference execution. Story properties, loads,
displacement, constitutive spring state, residual, tangent, tridiagonal work vectors, line-search
trial state and recovered result remain in device memory for the whole solve. The host does not
poll a residual, choose a line-search step, solve a tangent system, synchronize, or transfer
intermediate state per iteration. FP64 contraction is disabled. Numerical exhaustion returns the
same converged/nonconverged result boundary as the CPU source. A HIP failure throws and there is
no CPU dispatch; `fallback_count=0` is invariant.

## Live parity and receipt

The dedicated executable compares all five Python-C1/CPU-C1 profiles: one-story elastic,
one-story P-delta with backtracking, three-story elastic P-delta, three-story plastic, and
mixed-sign plastic loading. Every successful profile executes twice and must be bitwise
deterministic. A sixth execution requires exact CPU/HIP status and iteration parity for exhausted
Newton iterations.

The source-bound receipt records:

- selected device id/name, runtime architecture, ROCm runtime/driver and compiler;
- compiled architecture plus SHA-256 of the HIP header/source and OCML/OCKL/ISA bitcode;
- maximum displacement, residual and recovered-result errors;
- H2D/D2H bytes and transfer counts, synchronization count, kernel launches and peak resident
  bytes against visible VRAM;
- device-resident model/Newton/tangent/result recovery, zero host intermediate/control transfers,
  deterministic FP64 and zero fallback.

Local RX 6900 XT (`gfx1030`) execution on ROCm 6.0.2 produced 11/11 passing solves, bitwise
repeats, exact status/iteration/plastic-story/line-search parity, zero measured displacement,
residual and recovery error, and fallback zero. This remains a C2 candidate: authoritative
promotion requires the same source SHA in the manual `native-hip-dedicated` workflow on the
protected `native-hip-approved` self-hosted runner.

## Remaining boundary

This does not expose a HIP selector through the append-only ABI/Rust C3 layer, execute arbitrary
ModelIR assembly, parallelize the bounded single-work-item reference, cover transient Newton,
authorize ROCm packages, or close C6. The nonlinear-static numerical capability therefore remains
sequentially at C1 until the protected C2 receipt exists. Its CPU checkpoint and product E2E stay
independently evidenced at C4/C5.
