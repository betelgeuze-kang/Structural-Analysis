# Engine v2 HIP FGMRES Fixed-Rank Coarse Slot Recurrence v1

- Status: implemented private live integration contract, non-promoting local candidate
- Milestone: v0.2.63
- Date: 2026-07-17
- Authority: [Engine v2 master roadmap](structural-solver-engine-v2-master-roadmap.md)
- Capability row: `hip_fgmres_fixed_rank_coarse_slot_recurrence_v1`
- Follow-ons: [v0.2.64 device terminal guard](engine-v2-hip-fgmres-fixed-rank-coarse-terminal-guard-v1.md), [v0.2.65 strict public receipt](engine-v2-hip-fgmres-fixed-rank-coarse-slot-recurrence-receipt-v1.md)

The boundary below records the v0.2.63 milestone. The v0.2.64 follow-on adds
the fifth same-stream terminal-guard launch and actual local guard execution
without retroactively promoting the earlier test-double evidence. The v0.2.65
follow-on adds a strict pointer-free public receipt/schema while keeping the
live execution context private.

## Purpose

This slice connects the v0.2.62 typed fixed-rank coarse slot to the live
canonical and global FGMRES recurrence owners. An exclusive process-local
route reserves the exact live checkpoint context and its exact fixed-rank
coarse child. It is mutually exclusive with the v0.2.61 additive overlay.

For every immutable `APPLY_JACOBI_INDEXED` coordinate, dispatch selects the
typed route before the legacy vector kernel. The route then submits the exact
gate/dot/solve/apply companion sequence through the recurrence RTC owner's
one-logical-row checkpoint reservation. The legacy Jacobi launch is skipped.

The canonical prefix and global suffix keep their existing logical operation
counts. The companion owner separately tracks physical accepted launches, and
the existing canonical/global parent fences acknowledge them without adding a
healthy synchronization point.

## Observed test-double integration

The focused full-route case used four immutable Jacobi coordinates:
`(1,0)`, `(1,1)`, `(2,0)`, and `(2,1)`. It observed:

- four logical typed-slot applications;
- zero legacy `APPLY_JACOBI_INDEXED` vector launches;
- sixteen accepted and sixteen parent-fence-acknowledged physical slot
  launches;
- one canonical and three global applications;
- exactly two parent-fence acknowledgements; and
- zero launches through the older generic coarse application owner.

The partial-prefix case accepted the full canonical four-launch slot and one
physical launch of the first global slot before rejection. The integration
remained poisoned, retained five physical acceptances until the parent fences,
acknowledged all five, and did not promote the partial global row to a
successful application.

These observations use sealed runtime and HIP launch test doubles. They are
not actual GPU numerical execution evidence.

## Lifetime and concurrency contract

The route validates exact phase owner, schedule epoch, restart/column
coordinate, logical index, pending-count bounds, runtime, architecture,
stream, device, and recurrence/coarse pointer authority before launch.

Open stores both parent identities before acquiring the first child lease, so
a failure while reserving the live route can return the already-acquired
coarse child lease. Healthy close rejects an incomplete canonical/global
sequence. Poisoned close still requires every physically accepted launch to
be acknowledged by the matching recurrence parent fence; directly clearing a
companion kernel's pending counter cannot substitute for that parent fence.

Live forwarding snapshots and validates the route under the live queue lock,
then releases that lock before calling the slot context. Route revalidation is
itself lock-protected. This removes the live-lock-to-slot-lock versus
slot-close-to-live-lock inversion while retaining fail-closed behavior if a
concurrent close wins the race.

## Verification

Current-source local verification:

- full replacement, incomplete close, and partial physical-prefix behavior,
  plus open rollback, parent-fence bypass rejection, and callback lock-order
  coverage, with the v0.2.64 terminal guard attached: `7 passed in 131.91s`;
- adjacent canonical predecessor, additive coarse overlay, and selected
  global normal/partial recurrence regression: `26 passed in 461.50s`;
- public API and capability matrix path/state/claim-boundary validation: `25
  passed in 1.96s`; and
- Ruff lint and format checks for the selected integration, RTC, and safety
  files: passed.

The source/ABI and HIPRTC owner evidence remain the v0.2.62 identities. This
slice changes only Python live integration and does not add public exports, so
the aggregate public counts remain Engine/Assembly/Solvers `1232/1040/66`.

## Claim boundary and next step

This v0.2.63 milestone proves a private process-local test-double integration
of the typed row replacement and did not publish a strict public recurrence
receipt or schema. The v0.2.64 follow-on proves standalone actual guard
publication, and v0.2.65 now publishes the route receipt/schema without
exporting the live context. The combined current route still does not prove
actual typed-slot module/numerical execution or integrated status publication
immediately following real dot/solve/apply work, authoritative integrated
full-solve CPU/GPU parity,
full-iteration host-copy zero, external `gfx1100`, AMG/domain decomposition,
mesh-independent iteration counts, end-to-end `O(N)`, speedup, signed
evidence, promotion eligibility, or commercial readiness.

The next implementation order is:

1. run an actual integrated local `gfx1030` full solve and compare the final
   vectors, counters, terminal record, and fixed-rank CPU reference;
2. obtain independent external `gfx1100` execution evidence; and
3. only then evaluate promotion and performance claims from those actual
   observations.
