# Engine v2 HIP FGMRES Fixed-Rank Coarse Terminal Guard v1

- Status: implemented device-direct terminal binding, non-promoting local candidate
- Milestone: v0.2.64
- Date: 2026-07-17
- Authority: [Engine v2 master roadmap](structural-solver-engine-v2-master-roadmap.md)
- Capability row: `hip_fgmres_fixed_rank_coarse_terminal_guard_v1`
- Predecessor: [v0.2.63 private live slot recurrence](engine-v2-hip-fgmres-fixed-rank-coarse-slot-recurrence-v1.md)
- Follow-on: [v0.2.65 strict public live-route receipt](engine-v2-hip-fgmres-fixed-rank-coarse-slot-recurrence-receipt-v1.md)

## Purpose

The typed fixed-rank coarse slot reports gate, dot, solve, and apply failures
through one device `coarse_status` word. This milestone appends a one-thread,
one-block guard to every selected slot on the same recurrence stream. The
guard reads that word and publishes the first non-inactive failure directly
into the frozen FGMRES control state and solve record. It performs no host
copy, host status branch, allocation, or intermediate synchronization.

Each selected `APPLY_JACOBI_INDEXED` coordinate therefore remains one logical
recurrence ledger row while using five physical launches:

1. typed slot gate;
2. deterministic fixed-rank dot;
3. bounded Cholesky solve;
4. coarse-plus-Jacobi apply; and
5. device terminal guard.

The exact inactive padding value, bit 31 alone, is a no-op. Bit 31 combined
with any other bit fails closed instead of hiding the accompanying error.
Other bits map to the existing recurrence errors: invalid geometry/gate to
invalid control, nonfinite input to nonfinite input, nonpositive factor to
Jacobi inverse, and nonfinite arithmetic to arithmetic overflow. Publication
uses the existing first-device-error-wins compare-and-swap path, failure
origin `vector`, and termination `orthogonalization_failed`.

## Frozen source, ABI, and owner

The package composes the byte-identical recurrence-v2 source followed by the
guard supplement. Current identities are:

- recurrence source: `sha256:a5b39fb976aa330eaffae74feb8561f241df662a21dc32354b8010af2bb1c93d`;
- guard supplement: `sha256:1c3760aae2324109cee60dffb0e5ee3894127168cc34592e83230c06f82e650f`;
- combined source: `sha256:ae39f1efb1845b4f1ea1e66e1ecc63def413dbd3ae0b6a4a510b32b4445c913e`;
  and
- terminal-guard ABI: `sha256:e8f4a09d7d54cebcd2386c3bfc3ce59308f9423963e8db666f67b691b3bad796`.

`HipRtcFgmresFixedRankCoarseTerminalGuardKernelV1` binds the exact guard
symbol and owns attempted, accepted, rejected, ambiguous, and `BaseException`
launch outcomes. It validates the status/control/record extents, alignment,
non-overlap, exact stream, runtime, architecture, and binding before launch.
Accepted or uncertain work prevents unload until the matching parent fence is
acknowledged. An uncertain launch also blocks every relaunch until that fence
is acknowledged. Compile publication, reentrant operation, rejected unload,
and uncertain unload follow the same fail-closed ownership rules as the typed
slot owner. If native unload has already returned success, an interruption
during Python finalization preserves the known-success disposition and a
retry finalizes handles without issuing a second native unload.

The recurrence RTC owner wraps slot `4` plus guard `1` in one pending
reservation and one launch-audit row. A guard rejection is still ambiguous at
the logical level because the slot prefix has already been accepted. The live
route separately accounts and acknowledges both physical owners at the
existing canonical/global parent fences. If open fails while one module
cleanup is temporarily rejected, the failed-open retry owner retains both
parent leases and both physical module owners until cleanup succeeds.

## Verification

Current-source evidence includes:

- exact source/ABI, drift rejection, pointer/alias/stream validation,
  rejected/ambiguous/base-exception ownership, fence, unload, compile handoff,
  and public packaging tests;
- exact-inactive/mixed-bit fail-closed behavior, fence-before-relaunch after
  uncertain launch, and known-success unload interruption recovery;
- HIPRTC source compilation for `gfx1030` and `gfx1100`;
- recurrence-ledger focused coverage showing one logical row for slot `4`
  plus guard `1`, including rejected and ambiguous guard outcomes;
- sealed full-route test-double coverage with logical applications `4`,
  legacy Jacobi launches `0`, slot accept/ack `16/16`, guard accept/ack `4/4`,
  and parent fences `2`; and
- actual local `gfx1030` module load and execution where a nonfinite coarse
  status changed the device solve record to numerical failure/code `43`,
  error bit `4`, and failure origin `2`. The measured guard launch window had
  H2D async, D2H async, and blocking D2H deltas of `0`.

Current device-visible reruns produced `21 passed in 8.16s` for the guard
suites, including both local `gfx1030` hardware tests. The observation remains
process-local, unsigned, and non-promoting. Guard plus typed-slot RTC lifecycle
safety produced `8 passed in 1.89s`; the v0.2.65 live
slot-plus-guard-and-receipt recurrence produced `7 passed in 130.89s`;
adjacent canonical/overlay/selected-global regression
produced `26 passed in 461.50s`; public API plus capability checks produced `25
passed in 1.96s`; and full recurrence RTC produced `141 passed in 46.18s`. The
independently rerun guard/live/full-RTC components total `169 passed`.

At this v0.2.64 boundary, aggregate public symbol counts were
Engine/Assembly/Solvers `1249/1057/66`. The guard plan and RTC owner were
public, while the live slot-recurrence route remained private and had no
strict public receipt/schema. The v0.2.65 follow-on keeps that execution
context private but adds a pointer-free strict public receipt/schema, bringing
the current counts to `1263/1071/66`.

## Claim boundary and next step

This v0.2.64 milestone proves direct device publication for the coarse status
word and actual local execution of the guard kernel. The v0.2.65 follow-on
proves the live route's strict pointer-free receipt contract. Neither proves
an actual integrated typed-slot full solve, authoritative CPU/GPU fixed-rank
numerical parity, full-iteration or process-wide host-copy zero, external `gfx1100` module
execution, AMG/domain decomposition, mesh-independent convergence,
end-to-end `O(N)`, speedup, signed/persistent hardware evidence, promotion
eligibility, or commercial readiness.

The next order is:

1. run the entire typed-slot recurrence on local `gfx1030` and compare final
   vectors, counters, status, and the CPU fixed-rank reference;
2. obtain independent external `gfx1100` execution evidence; and
3. only then evaluate promotion and performance claims.
