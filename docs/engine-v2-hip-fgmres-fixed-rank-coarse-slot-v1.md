# Engine v2 HIP FGMRES Fixed-Rank Coarse Slot v1

- Status: implemented source/loader contract, non-promoting local candidate
- Milestone: v0.2.62
- Date: 2026-07-17
- Authority: [Engine v2 master roadmap](structural-solver-engine-v2-master-roadmap.md)
- Capability row: `hip_fgmres_fixed_rank_coarse_slot_v1`
- Follow-on: [v0.2.63 private live recurrence integration](engine-v2-hip-fgmres-fixed-rank-coarse-slot-recurrence-v1.md)

The “not live-connected” boundary below records the v0.2.62 milestone. The
follow-on document records the current private test-double integration without
retroactively promoting this source/loader evidence.

## Purpose

This slice defines and owns a typed `fixed-rank-coarse-or-Jacobi` recurrence
slot without changing the frozen recurrence-v2 or coarse-v1 source bytes. The
package composes the exact recurrence source, the coarse source inside the
`engine_v2_coarse_v1` namespace, and one slot supplement into a single HIPRTC
translation unit.

For the selected fixed-rank route, one logical `APPLY_JACOBI_INDEXED` schedule
row maps to four ordered physical launches on one stream:

1. slot gate: validate the exact recurrence coordinate, claim its schedule
   epoch, initialize the bounded coarse workspace, and publish gate failures
   to the existing terminal record;
2. deterministic fixed-rank dot;
3. bounded rank-at-most-16 Cholesky solve; and
4. slot apply: write `Zc + D^-1(r - A Zc)` to the indexed preconditioned basis.

The source contract records one logical operation, zero legacy Jacobi kernel
launches, one schedule-epoch claim, and four physical launches. Inactive
padding is marked with status bit 31 and does not claim an epoch or read/write
the numerical vectors.

## Frozen source and ABI identity

The current package-owned identities are:

- recurrence source: `sha256:a5b39fb976aa330eaffae74feb8561f241df662a21dc32354b8010af2bb1c93d`;
- coarse source: `sha256:d7a20e808b0f26a860e13e91a54b3a39c123fbc1b628e01d85cec94e06f5912a`;
- slot supplement: `sha256:91fcc3b0172a2f23599153fff966a03412068e07826b77f844b5fe4fbabe5633`;
- combined source: `sha256:6035e258eb208cfce672bd40f7e643b43026fc4b7caac321520af212c1cbf1fd`;
  and
- typed-slot kernel ABI: `sha256:412b0a8ae0ac6e32a1901141e78983c31746db08f650a83076c2e8318b136c69`.

The plan reloads and hashes all three resources for every identity operation.
It rejects recurrence-source drift, component drift, combined-source drift,
symbol/order drift, and coherently rehashed identity-field forgery.

## HIPRTC owner and lifetime

`HipRtcFgmresFixedRankCoarseSlotKernelV1` compiles, loads, and binds the exact
gate/dot/solve/apply symbol tuple. Before any native launch it validates exact
integer dimensions and coordinates, full pointer extents, alignment,
`uintptr` fit, and pairwise non-overlap for the eleven recurrence/coarse
buffers.

The owner tracks attempted, accepted, and uncertain work. A rejected launch
preserves the exact accepted prefix; an exception or `BaseException` pre-arms
uncertain same-stream ownership. Neither accepted nor uncertain work may be
unloaded until the matching external recurrence fence is acknowledged.
Concurrent module operations are serialized and reentrant native callbacks
fail closed without deadlock.

Module publication uses a one-shot task-local handoff so interruption across
the compiler return/STORE boundary cannot orphan a loaded module. Rejected
unload remains retryable, uncertain unload is terminally non-retryable, and an
interruption after successful native unload completes Python finalization
without issuing a second unload.

The frozen recurrence RTC owner also exposes a private typed-slot seam. It
reserves one checkpoint pending operation and one launch-audit ledger row
around the companion owner's four physical launches. A rejection before any
physical acceptance rolls back that logical reservation; a partial or
ambiguous acceptance retains it until the recurrence fence is acknowledged.
At v0.2.62 this closed raw RTC accounting, but no canonical/global live
context selected the seam in that milestone.

## Public surface and verification

The slot plan exports 12 symbols and the RTC owner exports 9. Current aggregate
public counts are Engine/Assembly/Solvers `1232/1040/66`, with unique,
identity-preserving re-exports.

Current-source local verification:

- source composition, ABI, forbidden-runtime-call, source-drift, and HIPRTC
  `gfx1030`/`gfx1100` compile contract: `7 passed`;
- typed-slot RTC launch, pointer, partial/ambiguous acceptance, fence, unload,
  compiler handoff, reentrancy, and concurrency coverage;
- finalization-interruption, unpublished-module cleanup, and coherently
  rehashed identity-drift safety coverage; and
- selected slot plan/RTC/safety/public/capability plus adjacent generic coarse
  RTC aggregate: `69 passed, 3 skipped in 5.76s`;
- typed-slot logical checkpoint reservation focused coverage: `3 passed`; and
- full adjacent recurrence RTC v2 suite: `137 passed in 44.63s`.

The three skips are hardware-only tests because `/dev/kfd` is unavailable in
this execution namespace. Both architecture source-compilation tests ran; no
actual typed-slot module load or numerical execution was observed here.

## Claim boundary and next step

This milestone proves a compile-time row-replacement contract, a hardened
four-launch HIPRTC owner, and raw recurrence checkpoint accounting for one
logical slot. The v0.2.62 milestone did not connect that route to the live
canonical/global recurrence contexts. Therefore this historical evidence does
not claim that a real recurrence skipped the legacy Jacobi launch.

It also does not prove direct terminal publication of numerical failures found
after the gate, actual integrated `gfx1030` full-solve parity, full-iteration
host-copy zero, external `gfx1100` execution, AMG/domain decomposition,
mesh-independent iteration counts, end-to-end `O(N)`, speedup, signed evidence,
promotion eligibility, or commercial readiness.

The next implementation step is an exclusive live typed-slot route that:

1. selects the slot before dispatching each fixed Jacobi schedule row;
2. submits the four physical launches instead of the legacy Jacobi kernel;
3. consumes the implemented one-logical-row reservation while separately
   accounting for the companion module's physical pending launches;
4. reuses the canonical/global parent fences without an extra healthy sync;
   and
5. binds all coarse numerical status bits into the device terminal record
   before subsequent recurrence work can be accepted.
