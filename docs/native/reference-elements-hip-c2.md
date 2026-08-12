# Bounded Reference Elements and Assembly HIP C2

Status: implementation and live local C2 candidate complete; protected-runner promotion pending.

## Product-owned path

`structural_elements_hip` is compiled only when `STRUCTURAL_ENABLE_HIP=ON`. It owns one bounded
FP64 batch path for the same truss3d, frame3d and three-node membrane profiles as the C++ CPU
reference source. The batch is sorted by stable element index, copied to the device once, and
processed by an element kernel followed by a deterministic dense-assembly kernel on the same
nonblocking stream. Element tangent, consistent mass, residual, JVP and recovery buffers remain
resident between those kernels. There is no CPU dispatch branch and `fallback_count=0` is part of
the receipt contract.

The assembly kernel assigns one work item to each global output and accumulates contributions in
stable-element then ascending-local-index order. It uses no atomics and compiles with FP
contraction disabled. The dedicated test runs the complete five-case CPU matrix, including a
rolled non-axis-aligned frame and tilted membrane, then requires every element and assembly value
to match and a second HIP run to be bitwise identical.

## Receipt

The live receipt records:

- device id/name and runtime `gfx` architecture;
- ROCm runtime and driver versions, compiler version and compiled architecture;
- SHA-256 of the HIP source/header and the exact OCML/OCKL/ISA device libraries;
- H2D/D2H byte and transfer counts, synchronization and kernel-launch counts;
- exact device-buffer bytes and visible VRAM capacity;
- FP64/deterministic policy, resident-between-kernels status, host-intermediate transfer count,
  fallback count and CPU/HIP maximum errors.

Local execution is deliberately reported as a C2 candidate. Authoritative promotion requires the
`native-hip-dedicated` workflow on labels `self-hosted, linux, x64, rocm,
structural-approved`, protected by the `native-hip-approved` repository environment. The workflow
uploads the raw device receipt, source-bound validation report and `rocminfo` inventory without
editing the protected product-readiness ledgers.

## Remaining boundary

This slice is dense reference assembly, not CSR, constraints, arbitrary ModelIR topology,
stateful nonlinear material execution, sparse Krylov/Newton, an ABI backend selector, checkpoint,
product E2E or C6. Until a protected workflow receipt exists, the capability manifest remains at
C1 even though the product-owned HIP implementation and local hardware candidate pass.
