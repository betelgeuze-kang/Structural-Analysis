# Generalized-Eigen Product C4/C5 Slice

Status: bounded dense CPU implementation evidence

This slice connects the existing ABI v1.9 modal and linear-buckling reference operations to a
strict Rust product path. It implements a C4 restart boundary and a C5 command-line E2E path for
one caller-supplied dense matrix problem of at most 128 DOFs. It does not promote the numerical
family beyond its current sequential C1 gate: an approved protected-runner C2 receipt is still
required before the HIP candidate can satisfy C2.

## Request and result boundary

structural-dense-spectral-request.v1 owns:

- one portable case identifier and an explicit modal or linear-buckling analysis kind;
- row-major stiffness and mass/geometric-stiffness matrices;
- optional positive coordinate recovery scales;
- an explicit bounded cyclic-Jacobi configuration; and
- the CPU backend selection.

Rust rejects duplicate keys, unknown fields, non-finite values, invalid dimensions and invalid
configuration before entering C++. The result contract separates rigid_mode_count from
finite_positive_eigenvalue_count, verifies modal frequency/period/Rayleigh relations and buckling
Rayleigh load factors, and binds request, model, state, execution and checkpoint identities.
ResultIR and ReportIR are canonical, self-hashed JSON with bounded_candidate authority.

## C4 checkpoint

The pointer-free little-endian SAEIGC01 artifact contains a fixed 184-byte header and the exact
canonical request payload. Its five SHA-256 bindings are:

1. request identity;
2. matrix/recovery-scale model identity;
3. validated-ready state identity;
4. analysis/backend/configuration/ABI execution identity; and
5. aggregate checkpoint identity including payload length and digest.

The C++ dense eigensolve is an atomic call. Consequently, the honest restart phase boundary is
validated_ready_for_atomic_native_solve; this slice does not invent a mid-Jacobi checkpoint.
Every single-byte artifact mutation, noncanonical embedded request and supplied-request drift
fails with checkpoint-mismatch code 1301 before native execution.

## C5 public flow

~~~bash
cargo run --manifest-path native/Cargo.toml -p structural-cli -- \
  analysis eigen-run request.json --output-dir direct

cargo run --manifest-path native/Cargo.toml -p structural-cli -- \
  analysis eigen-resume request.json direct/checkpoint.eigcp \
  --output-dir resumed
~~~

Publication is create-new and atomic. An existing destination is never overwritten. Each
successful directory contains:

- checkpoint.eigcp;
- result-ir.json;
- report-ir.json;
- report.md; and
- run-receipt.json.

The integration test clears the process environment and sets an unusable PATH; both modal and
buckling direct/resume runs still produce byte-identical directories with no Python/Node lookup
and fallback count zero.

## Evidence and remaining authority

- Rust contract wire tests cover strict parsing, derived-value consistency and ResultIR/ReportIR
  self-hash rejection.
- Runtime tests cover all identity bindings, every single-byte checkpoint mutation, request drift
  and bitwise direct/resume results.
- CLI tests cover both analysis kinds, a clean environment, atomic publication, corruption,
  request drift and existing-destination refusal.
- scripts/check_native_generalized_eigen_product.py makes the source, test, documentation and
  capability evidence fail closed in hosted CI.

Still open are the protected-runner C2 approval, sparse/subspace extraction, ModelIR-to-operator
adaptation, durable queued jobs for this analysis family, whole-model engineering authority,
spectral PDF rendering and C6 decommission. Python remains the broader oracle and rollback owner
until those sequential gates close.
