# Engine v2 HIP FGMRES Fixed-Rank Coarse Application Plan v1

Status: v0.2.57 contract, safety-hardened at v0.2.59, consumed by the v0.2.60 live context
Scope: fixed-source HIP application plan/source ABI; the plan itself owns no live resource
Promotion: contract-only and non-promoting

## Purpose

This increment binds the v0.2.55 CPU fixed-rank coarse-space artifact to the
exact device-buffer layout of one `HipFgmresPlanV1`. It defines the narrow
replacement seam for recurrence-v2's Jacobi-only
`basis_v[logical_index] -> preconditioned_basis_z[logical_index]` operation.

The physical basis `Z`, retained sparse operator images `AZ`, and small
Cholesky factor `L` remain the exact arrays validated by the CPU artifact. The
plan does not grant them numerical authority on HIP; it only fixes their device
layout, upload boundary, kernel source identity, launch order, and fail-closed
status propagation for the next live-runtime slice.

## Application ABI

For fixed rank `k <= 16`, one same-stream application is:

```text
0. prepare: zero g, c, and device status
1. dot:     g = Z^T r
2. solve:   L L^T c = g
3. apply:   z = Zc + diag(A)^-1 (r - AZc)
```

The package-owned source exposes four exact symbols:

- `engine_v2_fgmres_fixed_rank_coarse_prepare_v1`
- `engine_v2_fgmres_fixed_rank_coarse_dot_v1`
- `engine_v2_fgmres_fixed_rank_coarse_solve_v1`
- `engine_v2_fgmres_fixed_rank_coarse_apply_v1`

The coarse dot uses one deterministic 256-thread block tree per retained mode.
The bounded Cholesky solve uses one thread and at most 16 entries. The final
application is row-parallel over free DOFs. Compilation disables FP contraction;
cross-architecture numerical parity still requires actual execution receipts.

## Memory and transfer boundary

The overlay borrows the parent FGMRES `jacobi_inverse`, `basis_v`, and
`preconditioned_basis_z` allocations. It owns six additive allocations:

| Buffer | Shape | Initialization |
| --- | ---: | --- |
| physical basis `Z` | `F x k` FP64 | one H2D before recurrence |
| operator basis `AZ` | `F x k` FP64 | one H2D before recurrence |
| Cholesky factor `L` | `k x k` FP64 | one H2D before recurrence |
| coarse right-hand side | `k` FP64 | prepare kernel per application |
| coarse coefficients | `k` FP64 | prepare kernel per application |
| device status | one `u32` | prepare kernel per application |

Static initialization is exactly three planned H2D copies totaling
`8 * (2 F k + k^2)` bytes. After initialization, one application plans:

- kernel launches: `4`,
- H2D/D2H copies: `0/0`,
- additional CSR applications: `0`,
- allocations and explicit synchronizations: `0/0`,
- dense `N x N` projector elements: `0`.

This is the application boundary only. It is not yet proof that a complete
FGMRES iteration performs no host copy or synchronization.

## Source and failure contract

The plan replays the exact FGMRES plan/memory-layout hashes, execution-plan
operator/numeric/partition hashes, coarse-space hash, and the data hashes of
`Z`, `AZ`, and `L`. It also replays all buffer extents, launch geometry,
fixed-source SHA-256, compile options, kernel ABI hash, memory-layout hash, and
canonical plan hash through a strict Draft 2020-12 schema.

The source has four device status bits for invalid geometry, nonfinite input,
nonpositive factors, and nonfinite arithmetic. The coarse-dot kernel admits an
upstream status through one block-uniform shared gate before any barrier.
Upstream dot/solve failure makes the apply kernel publish NaN rows; a numerical
failure discovered during apply publishes device status plus at least one
canonical NaN sentinel without a host read. The v0.2.60 live context owns and
launches this ABI, but a later recurrence integration must still bind status to
the canonical FGMRES terminal-state machine rather than treating it as a
detached diagnostic.

The runtime ABI requires all FP64/u32 pointers to satisfy natural alignment,
their full derived byte ranges to fit uintptr, and all nine ranges to be
disjoint. The apply grid formula remains defined at the maximum accepted i32
free-DOF count.

## Current verification

- plan/schema/source/adversarial focused set: `16 passed`
- package-owned source compiled through HIPRTC for both `gfx1030` and `gfx1100`
  with an empty compile log
- current source:
  `sha256:d7a20e808b0f26a860e13e91a54b3a39c123fbc1b628e01d85cec94e06f5912a`
- current kernel ABI:
  `sha256:d79dbc97b02e318c7b8ba719d25aeb045c98a5412ac558f24676bc8f37841191`
- source guards confirm exact four symbols and no `hipMalloc`, `hipFree`,
  `hipMemcpy`, `hipStreamSynchronize`, or CSR row/column traversal
- deterministic plan replay confirms three parent borrows, six owned extents,
  three static uploads, four application launches, and application transfer
  counts `0/0`
- Current Engine/Assembly/Solvers public surfaces are unique at `1196/1004/66`; all
  `16` plan symbols preserve object identity through both public boundaries,
  and the schema/kernel resources are package-readable

This v0.2.57 plan milestone remains a compile observation. Downstream v0.2.59
reran the exact safety-hardened source on local `gfx1030` and observed `4/4`
launches, status `0`, application-window copy deltas `0/0/0`, and exact CPU
FP64 equality. That diagnostic does not retroactively make this plan a live
allocation-lineage or recurrence-integration receipt. The additive v0.2.60
context now provides allocation-lineage ownership and exact parent delegation
under adversarial test-double verification. Its separate required local
`gfx1030` gate also opened the live context and observed exact CPU FP64 parity,
status `0`, and application copy delta `0/0/0`. That downstream process-local
observation does not retroactively promote this contract-only plan or establish
recurrence integration.

## Explicit exclusions

This increment does not establish:

- a loaded/co-owned HIP module or allocation-lineage-safe live context,
- actual device execution or CPU/HIP coarse-application parity,
- canonical recurrence-v2 state-machine integration,
- transitive or iteration-wide host-copy zero,
- actual AMG/DD levels, interpolation, smoothers, or partition modes,
- mesh-independent iteration counts or end-to-end `O(N)`,
- speedup, `gfx1100` hardware execution, promotion, or commercial readiness.

## Next steps

1. Extend the safety-hardened current-source `gfx1030` run with
   nonfinite/status adversarial vectors.
2. Replace recurrence-v2 `APPLY_JACOBI_INDEXED` in a process-local integrated
   path and bind device status to the existing terminal failure state.
3. Audit the complete recurrence window for H2D/D2H/sync/allocation deltas,
   then repeat the same artifact on an external `gfx1100` runner.
