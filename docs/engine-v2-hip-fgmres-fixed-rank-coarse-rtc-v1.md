# Engine v2 HIP FGMRES Fixed-Rank Coarse HIPRTC Loader v1

Status: v0.2.59 safety hardening with v0.2.60 internal-owner handoff
Scope: fixed-source four-symbol loader and current-source local diagnostic
Promotion: non-promoting process-local observation

## Purpose

This increment loads the v0.2.57 fixed-rank coarse source as one HIPRTC module,
binds all four exact symbols, and owns their pending same-stream work until an
external fence is acknowledged. The v0.2.59 revision hardens the launch,
pointer-range, barrier, and unload boundaries found during adversarial review.
The additive v0.2.60 allocation-lineage child context consumes this owner, but
the module is not yet integrated into the canonical recurrence program.

## Loader contract

The loader binds:

```text
prepare -> coarse dot -> bounded Cholesky solve -> coarse+Jacobi apply
```

It validates the fixed source, ABI hash, compile options, architecture, HIPRTC
and HIP runtime library identities, code-object bytes, four function bindings,
and canonical identity hash. One application accepts exactly four launches.

Every native launch is pessimistically marked uncertain before crossing the
native boundary, then records attempted and accepted counts. A rejected launch
preserves the exact accepted prefix; a raised native exception leaves the
stream outcome ambiguous. Any accepted or ambiguous work prevents module unload
until the caller acknowledges a matching same-stream fence.

All nine device-buffer arguments are checked using their full derived extents,
not only base equality. FP64/u32 alignment, exclusive-end uintptr overflow, and
every interior overlap are rejected before launch. Dimension/rank/logical-column
errors, stream substitution, and mutated symbol bindings also fail before the
affected native call.

The coarse-dot status admission is block-uniform before its first barrier, and
the apply grid formula uses unsigned arithmetic at the `i32` upper boundary.
An exception from `hipModuleUnload` makes the unload outcome terminally
uncertain and prevents a second unload call; an explicit nonzero rejection
remains safely retryable. Launch, fence acknowledgement, and close are
serialized per loaded module, so concurrent same-stream applications cannot
interleave their four native calls. A same-thread native callback that attempts
to reenter any module operation fails closed instead of deadlocking.

The loader itself does not allocate, upload, download, synchronize, or select a
CPU fallback.

## Current-source verification

The safety-hardened current source is:

- source: `sha256:d7a20e808b0f26a860e13e91a54b3a39c123fbc1b628e01d85cec94e06f5912a`,
- kernel ABI: `sha256:d79dbc97b02e318c7b8ba719d25aeb045c98a5412ac558f24676bc8f37841191`,
- `gfx1030` compile-only code object: `16,744` bytes,
  `sha256:df308fa0f9edbf2cb6bff566fe94e442378531e87d49c5bd09f0bfaadccb18e4`,
- `gfx1100` compile-only code object: `17,448` bytes,
  `sha256:a2cfb952b6fb90ae3a42cc823eb495aa94e5bf5d8ec4980d2ca63dc78f64b0f2`,
- current test inventory: plan `16`, loader `19`, public `2`,
- current restricted-namespace run: `35 passed, 2 hardware skipped in 12.39s`,
- current device-visible root run: `37 passed in 13.58s`, including both
  hardware cases and the additive two-thread serialization case,
- two-thread serialization: passed without a second native call entering while
  the first application held the module operation lock,
- reentrant native callback operation: rejected without deadlock,
- v0.2.60 compile handoff return-boundary/direct interruption: `2 passed`,
- v0.2.60 restricted plan/loader/public run: `37 passed, 2 hardware skipped in 12.33s`,
- v0.2.60 required allocation-lineage live-context `gfx1030` gate:
  `1 passed in 23.23s`,
- current public surfaces: Engine/Assembly/Solvers `1196/1004/66`.

Both source-only HIPRTC compilations completed with empty logs. A device-visible
root namespace then ran the two `gfx1030` hardware tests against these exact
current bytes: `2 passed in 2.95s`. The loaded current-source identity is
`sha256:4646cffbb2203dcf7376d18cdb0a5567e8d1be1e9b5cad66f86a70cc1d63ea3d`.
The separate v0.2.60 live-context gate reused that current source through the
allocation-lineage parent3/owned6 path and observed `4/4` accepted and fenced
launches, status `0`, application copy delta `0/0/0`, and exact CPU FP64 parity.

## Current-source local actual-device observation

The safety-hardened `sha256:d7a20e80…f5912` source compiled, loaded, bound, and
closed on the local `gfx1030`. A second test built the v0.2.55 rank-2 coarse
artifact for `F=6`, enqueued all four kernels, fenced the exact stream, and
observed:

- bound symbols and accepted application launches: `4/4` and `4/4`,
- device status: `0`,
- application-window H2D async / D2H async / blocking D2H deltas: `0/0/0`,
- CPU-versus-HIP output: exact FP64 array equality, maximum absolute error `0.0`,
- current code object: `16,744` bytes,
  `sha256:df308fa0f9edbf2cb6bff566fe94e442378531e87d49c5bd09f0bfaadccb18e4`.

The diagnostic still performs five setup H2D uploads and two post-fence
blocking D2H reads, and it uses raw diagnostic allocations rather than the
canonical allocation-lineage owner. This is an unsigned process-local
observation, not persistent hardware or promotion evidence.

## Superseded v0.2.58 device observation

A focused diagnostic harness previously used source
`sha256:feaad0d5af0fc2ecbb1d8536ff382d40551c4b279bed6e3e36d62a7fb251e50d`
on a local `gfx1030` device:

- HIPRTC code object: `16,744` bytes,
- bound symbols: `4/4`,
- one application: `4/4` accepted launches,
- device status after the application: `0`,
- Engine-v2 bound-copy delta during the application window:
  H2D async `0`, D2H async `0`, blocking D2H `0`,
- retained rank: `2`, free DOFs: `6`,
- output versus the v0.2.55 CPU coarse application: exact FP64 array equality,
  maximum absolute error `0.0`.

The diagnostic setup performed five H2D uploads for Jacobi inverse, one source
`basis_v` slab, `Z`, `AZ`, and `L`. After the same-stream completion fence it
performed two blocking D2H reads for the output slab and device status. Those
setup/export transfers are outside the measured application window and remain
visible; they are not reclassified as host-copy zero.

The historical local identity was
`sha256:04334b9a91e0810d1d3623e474eeb676392e99225f75179a42dc9513f3da1b9e`.
It is unsigned, process-local, and tied to superseded kernel bytes. It remains
historical diagnostic context only and, by itself, is not evidence for the
v0.2.59 source; the current-source observation above is a separate run.

## Claim boundary

This increment establishes current-source compile/load/launch diagnostic
parity, strict loader contracts, and adversarial lifecycle behavior. v0.2.60
adds a one-shot task-local internal compile handoff so a published kernel is
recovered across the compiler-return/context-store interruption boundary. The
loader itself does not establish:

- allocation-lineage or exact-parent-delegation authority in its own receipt
  (the separate v0.2.60 context provides that non-promoting slice),
- replacement of `APPLY_JACOBI_INDEXED` inside a complete FGMRES solve,
- binding of device status to canonical terminal failure state,
- process-wide or full-iteration host-copy zero,
- interruption-safe module handoff for every Python trace boundary,
- external `gfx1100` module load/execution,
- AMG/DD hierarchy, mesh-independent iteration, or end-to-end `O(N)`,
- speedup, promotion, signed evidence, or commercial readiness.

## Next steps

1. Extend the current-source local `gfx1030` run with nonfinite/status
   adversarial device vectors and terminal-state propagation checks.
2. Bind the four-launch result/status to recurrence-v2's control and
   solve-record terminal failure path.
3. Execute an entire FGMRES solve with coarse preconditioning, then audit the
   full iteration window and compare iteration history/solution/residual against
   the CPU result.
4. Repeat the same final artifact on external `gfx1100` and preserve signed,
   persistent provenance before any multiarchitecture claim.
