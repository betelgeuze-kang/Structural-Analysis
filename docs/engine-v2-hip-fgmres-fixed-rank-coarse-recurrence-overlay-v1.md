# Engine v2 HIP FGMRES Fixed-Rank Coarse Recurrence Overlay v1

- Status: implemented, non-promoting local candidate
- Milestone: v0.2.61
- Date: 2026-07-17
- Authority: [Engine v2 master roadmap](structural-solver-engine-v2-master-roadmap.md)
- Capability row: `hip_fgmres_fixed_rank_coarse_recurrence_overlay_v1`

## Purpose

This slice connects the existing fixed-rank coarse HIP application to the
accepted FGMRES recurrence-v2 execution path. It reserves one exact live
checkpoint context and one pristine coarse execution context, derives every
fixed `(restart, column)` Jacobi coordinate from the immutable global schedule,
and admits applications only in that order.

The existing `APPLY_JACOBI_INDEXED` recurrence row is deliberately retained.
Immediately after each accepted Jacobi row, the overlay enqueues the exact four
coarse kernels on the same stream. The final coarse apply overwrites
`preconditioned_basis_z` before `PRECONDITION_ACCEPT` and the subsequent
Arnoldi SpMV consume it. This is an integrated numerical data path, but it is
an additive overlay, not a replacement of the legacy Jacobi launch or its ABI,
epoch, and counter semantics.

## Ordering and fence contract

For a fixed schedule with `R` restart cycles and restart dimension `M`, the
overlay expects exactly `R*M` applications:

1. the first application is owned by the canonical predecessor prefix;
2. all remaining applications are owned by the global recurrence suffix;
3. each retained Jacobi row is followed immediately by four coarse launches;
4. the canonical and global recurrence fences acknowledge the coarse module's
   already-submitted same-stream work; and
5. no additional coarse runtime synchronization is inserted on the healthy
   integrated path.

The receipt binds the full, sealed-prefix, and continuation schedule hashes;
both recurrence and coarse kernel identities/source hashes; exact live/coarse
context receipts; ordered application coordinates; the final global recurrence
receipt; and, when explicitly supplied, the exact downstream terminal outcome
observation.

## Failure and lifetime behavior

Only one overlay may reserve the exact live/coarse pair. Direct coarse
applications and coarse close are rejected while the route is active. Wrong
coordinates, owner objects, phases, counts, receipt hashes, and schema fields
fail closed.

If a coarse application is partially accepted and then fails, accepted coarse
work remains pending until the already-required parent recurrence fence is
observed. The coarse and overlay contexts become poisoned immediately. Shared
primitive poison publication is deferred only long enough for the active
global, sealed, canonical, overlay, and coarse owners to return their exact
leases; it is published when the live context begins terminal cleanup. This
does not admit another application or a second coarse child.

Failure telemetry distinguishes the retained Jacobi row from completed coarse
applications and exact known-accepted physical coarse launches. For example,
one complete canonical application followed by a global PREPARE acceptance and
DOT rejection is represented as two Jacobi rows, one completed application,
five accepted coarse launches, and five fence acknowledgements. It is not
silently reduced to the last complete four-launch bundle.

External fence acknowledgement is monotonic across an interruption after the
kernel acknowledgement was stored but before the context flag was stored.
Closing an unused overlay is valid and cannot publish integrated execution
claims.

## Receipt and public surface

The strict Draft 2020-12 schema is
`hip_fgmres_fixed_rank_coarse_recurrence_overlay_v1.schema.json`. Serialized
receipts contain hashes, dimensions, counters, coordinates, and claim flags;
they do not contain raw pointers, streams, modules, owner identities, leases,
or process-local tokens.

The module exports 15 public symbols. Current aggregate public counts are
Engine/Assembly/Solvers `1211/1019/66`, with identity-preserving re-exports.

## Claim boundary

The healthy test-double receipt can prove, for its exact process-local run:

- all fixed Jacobi coordinates were covered in canonical/global order;
- the retained Jacobi row and four coarse launches were same-stream ordered;
- the coarse output was ordered before downstream recurrence consumption;
- the two parent fence boundaries acknowledged the coarse launches;
- the overlay application window added no H2D, D2H, allocation,
  synchronization, or CSR apply; and
- the exact final global receipt, and optionally the exact downstream terminal
  observation receipt, were bound.

It does not prove or claim:

- removal or replacement of `APPLY_JACOBI_INDEXED`;
- direct coarse device-status binding into the terminal state machine;
- current-source actual-device integrated overlay execution or authoritative
  full-solve numerical parity;
- process-wide or full-iteration host-copy zero;
- external `gfx1100`, AMG/domain decomposition, mesh-independent iteration
  counts, end-to-end `O(N)`, or speedup;
- persistent/signed hardware provenance, ResultIR/design-code authority,
  promotion eligibility, or commercial readiness.

## Verification

Focused coverage includes fixed-coordinate interleaving, exact launch/fence
accounting, zero additional application activity, exclusive lifetime and
coordinate forgery, strict schema/hash and pointer-free serialization,
downstream terminal-observer binding, fence acknowledgement interruption
recovery, partial accepted-launch poison cleanup, close-before-run false claims,
healthy close rejection before a parent fence acknowledges pending coarse work,
and coherently rehashed status/terminal/reason forgery rejection. Adjacent legacy
canonical/global/live/coarse suites remain required to confirm that the
no-overlay recurrence behavior is unchanged.

Current-source local results:

- focused overlay integration/adversarial suite: `8 passed in 239.62s`;
- public API/package schema plus capability matrix: `22 passed in 1.99s`;
- adjacent coarse context: `24 passed in 190.08s`;
- adjacent live checkpoint context: `42 passed in 204.33s`;
- adjacent canonical predecessor: `14 passed in 113.18s`;
- adjacent sealed checkpoint transaction: `30 passed in 449.24s`;
- adjacent global recurrence: `54 passed in 1212.23s (0:20:12)`; and
- cross-surface public-count compatibility: `9 passed in 42.47s`.

These are local test-double and contract regressions. No current-source actual
device run of the integrated overlay was performed for this milestone.
