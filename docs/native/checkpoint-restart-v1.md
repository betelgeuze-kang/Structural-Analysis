# Nonlinear NDTHA Checkpoint/Restart v1

## Scope and authority

This contract closes C4 only for the bounded serial-FP64 CPU nonlinear-NDTHA profile already
transported through ABI v1.5. It does not promote the solver family beyond its existing C1 oracle
matrix and does not claim HIP parity, a durable job state machine, process-crash recovery or
product E2E.

`structural-runtime` is the serialization and persistence owner. C++ remains the numerical-state
validator and executor through the single `sa_get_api_v1` table. No process pointer, allocation
address or Rust/C++ object representation is persisted.

## Canonical artifact

Every integer and IEEE-754 binary64 bit pattern is encoded little-endian. Vector lengths are
unsigned 64-bit values; booleans are one canonical byte, `0` or `1`. The artifact is capped at
256 MiB and each vector at 1,000,000 values.

| Offset | Size | Field |
|---:|---:|---|
| 0 | 8 | ASCII magic `SANDCP01` |
| 8 | 4 | format version, `1` |
| 12 | 4 | header size, `152` |
| 16 | 8 | state payload byte count |
| 24 | 32 | model SHA-256 |
| 56 | 32 | state SHA-256 |
| 88 | 32 | execution SHA-256 |
| 120 | 32 | aggregate checkpoint SHA-256 |
| 152 | variable | canonical state payload |

The payload contains, in fixed order, its version; next step; execution status; collapse and
iteration summaries; displacement, velocity and acceleration; and all eleven response channels.
Decode rejects a bad magic/version/header, truncation, trailing bytes, integer overflow,
non-finite values, non-canonical booleans, unbounded extents and unknown status values.

## Identity binding

All hashes use SHA-256 with distinct NUL-terminated domain labels.

- Model identity binds story count and stiffness, height, axial load, yield drift, mass and damping.
- State identity binds the exact canonical state payload.
- Execution identity binds algorithm id, CPU backend, ABI v1.5, every solver setting, floor load
  and acceleration record.
- Aggregate identity binds the three digests and payload length.

Restore first verifies byte integrity and model/execution identity, then submits the decoded state
to the ABI v1.5 advance operation with a zero-step budget. Native semantic rejection maps to the
stable checkpoint-mismatch taxonomy; no partially restored state is published.

## Persistence and restart guarantee

For the supported Linux filesystem profile, persistence uses a create-new temporary file in the
destination directory, complete write, file `sync_all`, rename and directory `sync_all`. A failure
before publication removes the temporary file. A successful reload and resume is bitwise identical
to the same execution run without interruption, including completion and collapse terminal states.

The frozen fixture receipt is asserted in Rust integration tests, and every possible single-byte
mutation of that artifact is rejected. Job submission/poll/cancel, process ownership and startup
reconciliation remain the next runtime slice rather than implied behavior of this file primitive.
