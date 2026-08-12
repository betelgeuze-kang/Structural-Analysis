# Sparse Linear Product C4/C5 Slice

Status: bounded canonical-CSR CPU implementation evidence

This slice connects the existing bounded Jacobi-PCG reference solver to ABI v1.10 resumable
execution, a strict Rust product contract, an exact C4 checkpoint and public C5 command-line
flows. It does not promote the sparse numerical family beyond C1: the product-owned HIP
candidate still needs an approved protected-runner C2 receipt before sequential C2/C3 acceptance.

## Request and result boundary

`structural-sparse-linear-request.v1` owns one canonical symmetric CSR matrix, right-hand side,
optional initial guess, bounded PCG configuration, portable case identifier and explicit CPU
backend. Rust rejects duplicate or unknown fields, non-finite values, inconsistent dimensions,
noncanonical column order, out-of-range indices and requests beyond the 100,000-order,
5,000,000-nonzero and 64 MiB product limits before entering C++.

The model identity binds matrix values, topology, right-hand side and initial guess. The execution
identity binds the algorithm, configuration, CPU backend and ABI v1.10. A converged result
recomputes the true residual from the request, verifies the native residual norms and emits
self-hashed `structural-sparse-linear-result-ir.v1` and
`structural-sparse-linear-report-ir.v1` documents with fallback count zero.

## ABI v1.10 restart boundary

ABI v1.10 appends `sparse_linear_begin` and `sparse_linear_advance` at table offsets 144 and 152.
The 280-byte `sa_sparse_linear_state_v1` contains complete scalar iteration metadata and four
caller-owned vectors: solution, residual, search direction and diagonal inverse. The C boundary
validates every version, size, reserved field, pointer, length, stride, extent and overlap, works
on a private copy and publishes only after success. Zero iteration budget is a validated no-op,
advancing a terminal state is idempotent, and numerical terminal states remain typed durable state
instead of being discarded as ABI transport errors.

## C4 checkpoint

The pointer-free little-endian `SAPCGC01` artifact contains a fixed 192-byte header, the exact
canonical request and a bit-preserving binary encoding of the complete PCG state. It binds five
SHA-256 identities:

1. strict request identity;
2. sparse model identity;
3. real iterative state identity;
4. execution/ABI/configuration identity; and
5. aggregate checkpoint identity including payload lengths and bytes.

Runtime tests checkpoint after a real iteration, serialize and restore the state, and prove that
segmented and direct execution produce bitwise-identical terminal checkpoints and ResultIR.
Every single-byte mutation, noncanonical embedded request and request/configuration drift fails
with checkpoint-mismatch code 1301 before further execution.

## C5 public flow

~~~bash
cargo run --manifest-path native/Cargo.toml -p structural-cli -- \
  analysis linear-run request.json --output-dir direct

cargo run --manifest-path native/Cargo.toml -p structural-cli -- \
  analysis linear-run request.json --output-dir partial --iteration-budget 1

cargo run --manifest-path native/Cargo.toml -p structural-cli -- \
  analysis linear-resume request.json partial/checkpoint.pcgcp \
  --output-dir resumed
~~~

Publication is create-new and atomic. Every boundary contains `checkpoint.pcgcp`,
`checkpoint-receipt.json` and a self-hashed `run-receipt.json`. A converged boundary additionally
contains `result-ir.json`, `report-ir.json` and deterministic `report.md`. A numerical failure
publishes its terminal checkpoint and typed receipt, then returns a nonzero process status.

The integration test clears the process environment, sets an unusable `PATH`, advances through a
real one-iteration boundary and proves direct/resumed terminal artifact directories are byte
identical with no Python/Node lookup. It also proves symlink input refusal, checkpoint tamper
rejection and non-overwrite publication behavior.

## Evidence and remaining authority

- C++ tests cover complete-state direct/segmented bit identity, zero-budget and terminal
  idempotence, corruption rejection and numerical terminal preservation.
- ABI and Rust FFI tests cover v1.0-v1.9 append-only compatibility, deep-copy ownership,
  overlap/extent validation, error taxonomy and JSON serialization at real iteration boundaries.
- Rust contract/runtime/report/CLI tests cover strict wire documents, every checkpoint byte,
  self-hashes, true residual reconstruction and clean-environment product artifacts.
- `scripts/check_native_sparse_linear_product.py` makes this evidence chain fail closed in hosted
  CI.

Still open are protected-runner C2 approval, ModelIR-to-arbitrary-CSR assembly, durable queued
jobs/API for this family, PDF projection, whole-model engineering acceptance, HIP product
execution and C6 decommission. Python remains the independent C1 oracle and rollback owner until
those sequential gates and release evidence close.
