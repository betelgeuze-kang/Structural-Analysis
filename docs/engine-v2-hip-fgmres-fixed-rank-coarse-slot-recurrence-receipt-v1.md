# Engine v2 HIP FGMRES Fixed-Rank Coarse Slot Recurrence Receipt v1

- Status: implemented strict public receipt/schema, private live context, non-promoting local candidate
- Milestone: v0.2.65
- Date: 2026-07-17
- Authority: [Engine v2 master roadmap](structural-solver-engine-v2-master-roadmap.md)
- Capability row: `hip_fgmres_fixed_rank_coarse_slot_recurrence_v1`
- Predecessor: [v0.2.64 device terminal guard](engine-v2-hip-fgmres-fixed-rank-coarse-terminal-guard-v1.md)

## Purpose

The v0.2.63/v0.2.64 route replaces every immutable recurrence
`APPLY_JACOBI_INDEXED` coordinate with one logical checkpoint-ledger row backed
by four typed-slot launches and one same-stream device terminal guard. This
milestone gives that private execution route a strict, pointer-free public
receipt without exporting the live context or its mutation API.

Each successful application row records:

- logical recurrence launches: `1`;
- legacy Jacobi launches: `0`;
- typed slot launches: `4`;
- terminal-guard launches: `1`; and
- total physical launches: `5`.

The receipt separately records slot and guard acceptance and parent-fence
acknowledgement. A partial global failure therefore cannot be represented as a
successful five-launch row. The observed partial prefix remains one successful
canonical row plus a poisoned second attempt with physical totals slot `5`,
guard `1`, all acknowledged before lease release.

## Strict schema and authority boundary

The public schema is
`hip_fgmres_fixed_rank_coarse_slot_recurrence_v1.schema.json`. It is Draft
2020-12, rejects unknown properties, and carries canonical SHA-256 hashes for
the receipt and application sequence. Current-source identities are:

- public receipt contract: `sha256:32ca94347689c43906243b4c296277e00c27fae9fa5689ff94ac663ff978b958`;
- private live integration: `sha256:52a75cfdf25328bce13bd996d96a4c3b4ec90a0b9cbb42ff2380d5b37d5ae942`;
  and
- strict schema: `sha256:a7f54e1f54c1f34c98d152ca0052bb9aa2da70b2ab8bf112a000b0ea5a56ed5d`.

Bindings cover the exact live and coarse opening receipts, FGMRES and coarse
plans, recurrence/coarse/slot/guard kernel identities and source hashes, full
and partitioned recurrence schedules, and the coordinate and schedule-epoch
sequences. Dimensions freeze the free DOF count, restart policy, retained
rank, expected application count, and the `1/0/4/1/5` logical/legacy/slot/guard
launch constants. The validator also fixes `maximum_restart_count` to
`ceil(max_iterations / restart_dimension)`, requires the full fixed-program
coordinate count `R*M`, and bounds retained rank by the free-DOF count. Schema
preflight applies the source-plan limits before coordinate materialization:
`M <= 16`, `I <= 4096`, padded applications `<= 4110`, and retained rank
`<= 16`. The application maximum is `max_M ceil(4096/M)*M`, not the raw
iteration limit; the maximum occurs at `M=15`.
Nested scalar values are exact-typed; `bool`-as-`int` and `str` subclass
aliases are rejected instead of being normalized into valid-looking wire data.
The final global receipt must also match a receipt rebuilt from the exact
global owner. This direct rebuild avoids acquiring the global lock while the
slot lock is held and preserves the established global-to-slot lock order.

No pointer, stream handle, module handle, function handle, owner identity,
lease ID, or process token is serialized. Hexadecimal pointer-like exception
details must already be redacted; an unredacted value is rejected.

Validation has two explicit authority levels:

1. detached validation proves strict schema, canonical hashes, and internal
   state/telemetry/claim consistency only; and
2. `expected_context` validation additionally proves process-local object
   provenance and freshness against the still-live private context.

A stale opening receipt is rejected after execution progresses. Coherently
rehashed status, context ID, telemetry, reason, and unknown-field forgeries are
also rejected. Coherently shortened schedules, oversized retained ranks,
foreign reason codes, and non-tuple application containers are rejected even
when their outer receipt hashes are recomputed. Reason detail is bounded to
`320` characters. A closed or cleanup-failed receipt must show every accepted
physical launch acknowledged. Parent-fence ordinal `1` acknowledges exactly
the accepted canonical prefix, capped at slot/guard `4/1`; ordinal `2`
acknowledges every accepted launch. Poison is terminal, so telemetry may carry
at most one failed attempt beyond its successful application rows. Directly
acknowledging the physical slot and guard owners cannot impersonate the
recurrence parent's fence; live receipt validation detects that mismatch.

## Claims and exclusions

After the full sealed test-double route is globally fenced and its exact global
receipt is bound, the strict receipt can assert all scheduled Jacobi rows were
replaced, one logical row maps to five physical launches, both physical owners
were parent-fenced, the device terminal binding contract is present, and the
application boundary introduces no H2D, D2H, allocation, synchronization, CSR
apply, host status branch, or fallback.

It always keeps the following claims false:

- actual integrated typed-slot device execution;
- authoritative CPU/GPU numerical parity;
- full-iteration or process-wide host-copy zero;
- end-to-end `O(N)`;
- speedup;
- commercial readiness; and
- promotion eligibility.

The live route remains private. The public surface contains only immutable
receipt value types, constants, and the validator.

## Verification

Current-source verification includes:

- live full-route, incomplete-close, partial-prefix, failed-open cleanup,
  lock-order, parent-fence bypass, strict receipt, and forgery coverage: `7
  passed in 131.45s`;
- public receipt module/schema packaging and identity-preserving re-export: `2
  passed in 1.80s`;
- capability plus public API checks: `25 passed in 2.06s`; and
- Ruff lint/format and JSON/schema parsing: passed.

The public Engine/Assembly/Solvers symbol counts are `1263/1071/66`; the
receipt module exports `14` unique names.

## Next step

PR #78 and its current branch are frozen as a source quarry; this milestone is
not extended in place. The master-roadmap current-main extraction sequence is
PR A core contracts, PR B equation scaling, PR C CPU FGMRES, PR D CPU
fixed-rank coarse, PR E backend-neutral result types, PR F HIP substrate, PR G
HIP fixed-rank coarse, PR H canonical full-solve integration, and PR I hardware
evidence. PR H must compare final vectors, counters, coarse status, solve record,
and the fixed-rank CPU reference without a hidden host branch. PR I then binds
the same source/wheel to self-hosted `gfx1030`, independent `gfx1100`, a signed
receipt, and the durable replay ledger. Until those extracted PRs pass, this
remains a strict public contract for a private test-double-integrated route,
not a promoted solver result.
