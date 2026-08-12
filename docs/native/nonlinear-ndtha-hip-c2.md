# Bounded Nonlinear-NDTHA HIP C2

Status: product-owned implementation and live local C2 candidate complete; protected-runner
promotion pending.

## Product-owned execution context

`structural_solver_hip` includes this path only with `STRUCTURAL_ENABLE_HIP=ON`. CPU and HIP call
the same `validate_nonlinear_ndtha_problem` contract and consume the same deterministic height
shape. The device constitutive assembly, tridiagonal solve and result recovery share one source
with the nonlinear-static HIP path. The current reference profile is bounded to 128 stories,
4,096 time steps, 64 adaptive attempts and 1,000 Newton iterations.

One HIP work item owns all time steps, adaptive load retry, Newmark prediction/update, Newton and
line-search control, tangent solution, collapse checks, constitutive state and eleven response
channels. Nine immutable model/record buffers enter before the kernel and twelve terminal result
buffers return after it. There is one launch and one final synchronization per solve, with zero
host intermediate-state, Newton-control or time-step-control transfers. FP64 contraction is
disabled; HIP errors throw and no CPU dispatch exists, so `fallback_count=0` is invariant.

## Live parity and receipt

The executable covers the five frozen Python-C1/CPU-C1 cases: elastic P-delta, one-story elastic,
plastic/backtracking, adaptive retry and physical collapse. Each runs twice for bitwise device
repeatability. A separate bounded numerical-exhaustion case fixes nonconvergence taxonomy. It
compares all response arrays, summaries, status, completed steps, adaptive iterations, plastic
counts and line-search backtracks.

Local RX 6900 XT (`gfx1030`) execution on ROCm 6.0.2 produced 11/11 passing solves, exact CPU/HIP
response and summary parity, bitwise repeats, 99 H2D and 132 D2H transfers in aggregate, one
kernel and synchronization per solve, and zero fallback. The receipt binds the public HIP header,
shared constitutive device header, kernel source, compiler, runtime device and OCML/OCKL/ISA
bitcode SHA-256.

This remains a C2 candidate. Authoritative C2 requires the identical source hash from the manual
`native-hip-dedicated` workflow in the protected `native-hip-approved` environment.

## Remaining boundary

This slice does not expose a HIP backend selector through the C ABI/Rust product path, accept
arbitrary ModelIR dynamic assembly, prove scalable parallel performance, authorize ROCm packages
or close C6. The nonlinear-NDTHA family therefore remains sequentially at C1 pending the protected
C2 receipt; its CPU restart and product E2E evidence remain independently bounded at C4/C5.
