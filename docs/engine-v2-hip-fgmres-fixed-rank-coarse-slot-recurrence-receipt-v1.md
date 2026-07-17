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
coordinate count `R*M`, and bounds retained rank by the free-DOF count.

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
physical launch acknowledged. Directly acknowledging the physical slot and
guard owners cannot impersonate the recurrence parent's fence; live receipt
validation detects that mismatch.

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
  passed in 130.89s`;
- public receipt module/schema packaging and identity-preserving re-export: `2
  passed in 1.80s`;
- capability plus public API checks: `25 passed in 1.96s`; and
- Ruff lint/format and JSON/schema parsing: passed.

The public Engine/Assembly/Solvers symbol counts are `1263/1071/66`; the
receipt module exports `14` unique names.

## Next step

The next evidence must execute the entire typed slot plus guard route on local
`gfx1030`, bind this receipt to that run, and compare final vectors, counters,
coarse status, solve record, and the fixed-rank CPU reference. Independent
external `gfx1100` execution follows. Until then, this remains a strict public
contract for a private test-double-integrated route, not a promoted solver
result.
