# Engine v2 HIP FGMRES Fixed-Rank Coarse Execution Context v1

Status: v0.2.60 local implementation candidate
Scope: exact live-parent delegation and allocation-lineage ownership for the fixed-rank coarse overlay
Promotion: non-promoting process-local resource/application evidence

## Purpose

This increment turns the v0.2.57 plan and v0.2.59 four-symbol HIPRTC owner into
one live resource overlay. It reuses the exact `jacobi_inverse`, `basis_v`, and
`preconditioned_basis_z` capabilities already held by a live FGMRES checkpoint
context and allocates the six coarse buffers through a peer allocation-lineage
owner.

It does not yet replace `APPLY_JACOBI_INDEXED` in the canonical recurrence-v2
program. The context is an independently callable, same-stream application
slice whose receipts remain non-promoting.

## Ownership model

The live checkpoint parent already holds the exclusive registry borrow that
contains the three source buffers. A second registry borrow would be invalid.
The parent therefore reserves one exact coarse child and issues a process-local
semantic delegation containing those same three capability objects, the same
group lease, runtime/device/stream authority, and immutable FGMRES/recurrence
bindings.

The child opens a peer owner named
`fgmres_fixed_rank_coarse_owned_buffers`, reserves exact owner control, and
allocates:

1. `coarse_physical_basis_z`
2. `coarse_operator_basis_az`
3. `coarse_cholesky_l`
4. `coarse_rhs`
5. `coarse_coefficients`
6. `coarse_status`

All six allocations are owner-minted capabilities. The serialized receipts do
not contain device pointers, owner identities, lease IDs, stream handles,
module handles, or function handles.

## Initialization and application boundary

Opening enqueues the immutable `Z`, `AZ`, and `L` arrays as exactly three H2D
operations on the parent stream, then observes one setup fence before issuing a
ready receipt. This setup work is intentionally outside the application
window.

One `enqueue_application(logical_index)` call submits the fixed order:

```text
prepare -> dot -> bounded Cholesky solve -> coarse+Jacobi apply
```

For that narrow call boundary the context performs:

- four accepted HIP module launches,
- zero H2D and zero D2H operations,
- zero allocation or free operations,
- zero explicit synchronization,
- zero additional CSR applications.

This is a construction and bound-runtime API claim for the coarse application
window. It is not a process-wide DMA audit and does not establish that a full
FGMRES iteration or solve is host-copy-free.

## Failure and cleanup contract

Launch accounting is pessimistic. A partial accepted prefix or ambiguous
native boundary poisons the coarse child and propagates uncertainty to the
live solver chain. Pending work must cross the exact parent-stream fence before
module unload or allocation retirement.

Terminal cleanup order is:

```text
same-stream fence
-> four-symbol module close or terminal unload quarantine
-> six owned buffers in reverse order
-> peer allocation owner close
-> live-parent semantic delegation release
```

An explicitly known-not-freed allocation remains retryable under the same
lease. Unknown free outcomes are quarantined through allocation-lineage
authority. An exception from module unload is terminally uncertain and is
never retried. The parent cannot close while the child is active, including
while retryable cleanup authority remains.

Internally compiled modules use a one-shot task-local weak route with a strong
handoff owner. If control is interrupted after compiler publication but before
the context stores the returned kernel, failed-open cleanup recovers and closes
that exact module once. A caller-supplied kernel is not consumed when parent
reservation or memory-budget admission fails before kernel preflight.

## Receipt contract

Two strict Draft 2020-12 schemas are packaged:

- `hip_fgmres_fixed_rank_coarse_context_v1.schema.json`
- `hip_fgmres_fixed_rank_coarse_application_v1.schema.json`

The context receipt binds the live parent opening receipt, FGMRES and recurrence
plans, coarse plan/space/layout, exact parent and owned capability generations,
HIPRTC identity, dimensions, six buffer descriptors, allocation-lineage
summary, monotonic telemetry, and explicit false claim boundary. The
application receipt binds the context, sequence, logical column, four accepted
launches, and the five zero-activity counters.

Standalone schema/hash validation proves structural consistency only.
Process-local provenance requires the retained exact context through
`expected_context`.

## Current verification

The current focused runs are:

- context lifecycle/adversarial suite: `24 passed in 190.73s`,
- plan/loader/public suite: `37 passed, 2 hardware skipped in 12.33s`,
- capability matrix: `19 passed in 0.24s`,
- adjacent live-checkpoint context suite: `42 passed in 203.57s`,
- adjacent RTC/public API suite: `45 passed in 50.81s`,
- required local `gfx1030` live-context hardware gate: `1 passed in 23.23s`.

The current test-double suite covers:

- exact parent-3 delegation and owned-6 allocation/final cleanup order,
- three static uploads plus one setup fence,
- four-launch application with zero application-window host/runtime activity,
- second-child and active-parent-close exclusion,
- memory-budget rejection before ownership,
- partial allocation rollback,
- partial launch poison followed by mandatory fence,
- retryable fence and known-not-freed failures,
- terminal uncertain module-unload quarantine,
- internal compiler return-boundary interruption with exactly one unload,
- pointer-free receipts, forgery rejection, strict packaged schemas, and public
  object-identity preservation.

The fixed-source/ABI hashes remain those of v0.2.59 because this increment does
not alter the HIP source:

- source: `sha256:d7a20e808b0f26a860e13e91a54b3a39c123fbc1b628e01d85cec94e06f5912a`
- kernel ABI: `sha256:d79dbc97b02e318c7b8ba719d25aeb045c98a5412ac558f24676bc8f37841191`

## Current-source local actual-device observation

The required live-context hardware gate opened this exact allocation-lineage
context on the local `gfx1030` through the internal compiler and closed the full
parent/child chain. It recorded:

- backend/origin/architecture: `hip` / `internally_compiled` / `gfx1030`,
- free DOFs / retained rank: `12 / 2`,
- coarse-owned device bytes: `452`,
- context static H2D: `3` operations / `416` bytes,
- setup plus application fence successes: `2`,
- application launches accepted/acknowledged: `4/4`,
- device coarse status: `0`,
- application-window H2D async / D2H async / blocking D2H deltas: `0/0/0`,
- CPU-versus-HIP output: exact FP64 array equality, maximum absolute error `0.0`,
- code object:
  `sha256:df308fa0f9edbf2cb6bff566fe94e442378531e87d49c5bd09f0bfaadccb18e4`,
- loaded identity:
  `sha256:4646cffbb2203dcf7376d18cdb0a5567e8d1be1e9b5cad66f86a70cc1d63ea3d`.

The numerical verification performs post-fence D2H reads of the parent basis,
output slab, and coarse status after the audited application window. Those
verification-only reads are visible and are not reclassified as host-copy
zero. The serialized context receipt also keeps
`actual_device_application_observed=false`: the required harness observation is
process-local, unsigned verification rather than a self-promoting receipt.

## Explicit exclusions

This increment does not establish:

- replacement of canonical recurrence-v2 Jacobi rows,
- device-status binding to the canonical terminal failure state,
- a complete FGMRES solve using the coarse overlay,
- broad-model or independent multiarchitecture parity for this live context,
- full-iteration or process-wide host-copy zero,
- external `gfx1100` module load or execution,
- AMG hierarchy, domain decomposition, or mesh-independent iteration counts,
- end-to-end `O(N)`, measured speedup, or workstation performance targets,
- signed/persistent provenance, promotion eligibility, or commercial readiness.

## Next steps

1. Replace the canonical recurrence-v2 Jacobi application row with a typed
   coarse-or-Jacobi operation while preserving all checkpoint epochs and
   failure-state semantics.
2. Bind `coarse_status` to the existing terminal control/solve-record path
   without an iteration D2H read or host branch.
3. Run a complete local `gfx1030` solve through the recurrence-integrated
   context and compare solution, true residual, restart history, and iteration
   count with the CPU coarse reference.
4. Audit the full recurrence window, then repeat the same source/artifact on an
   independent external `gfx1100` runner before any multiarchitecture claim.
