# ModelIR Modal Product C5 Slice

Status: bounded local CPU implementation evidence

This slice connects the existing typed Frame3D/Truss3D `ModelIR` assembly to the existing ABI
v1.9 dense modal solver. It is a local C5 product path for at most 128 active DOFs. It does not
promote the generalized-eigen numerical family beyond C1 and does not claim sparse whole-model,
linear-buckling, installed-distribution, or engineering authority.

## Strict request and assembly boundary

`structural-model-ir-modal-analysis-request.v1` binds:

- the exact ModelIR content, semantic, and provenance identities;
- one portable case identifier and CPU backend;
- one existing linear load-pattern identifier needed by the append-only ABI v1.14 assembly
  entrypoint; and
- the bounded modal mode count, sweep limit, and validation tolerances.

The selected load pattern only opens the current zero-state assembly surface. Its external-load
vector is recorded but not consumed by modal execution. Rust rejects duplicate or unknown fields,
identity drift, unsupported ModelIR graphs, fallback, more than 128 active DOFs, excessive mode
counts, malformed canonical CSR, non-finite values, and asymmetric active `K/M` operators.

The adapter deterministically expands the active canonical CSR stiffness and consistent-mass
arrays into row-major dense matrices. It then builds the existing strict
`structural-dense-spectral-request.v1` modal request and crosses the already verified ABI v1.9
cyclic-Jacobi path. Linear buckling remains open because this assembly path does not construct a
load-dependent geometric stiffness matrix.

## Public local flow

~~~bash
cargo run --manifest-path native/Cargo.toml -p structural-cli -- \
  analysis model-modal-run model.json modal-request.json --output-dir result
~~~

Publication is create-new and atomic. A successful directory contains:

- the canonical `model-ir.json` and `model-modal-request.json`;
- `assembly-receipt.json` and `generated-dense-request.json`;
- the dense phase boundary `checkpoint.eigcp`;
- self-hashed `result-ir.json`, `report-ir.json`, and deterministic `report.md`;
- the nested `dense-run-receipt.json`; and
- the outer self-hashed `run-receipt.json` binding all prior artifacts.

The checkpoint is matrix-bound but is not yet an outer ModelIR-bound restart contract. This first
public command therefore exposes run only; `model-modal-resume` is intentionally absent.

## Verification and remaining authority

The focused product case is the repository's two-node Frame3D cantilever: C++ ABI v1.14 produces
six active DOFs, Rust adapts the exact `K/M` pair, and ABI v1.9 returns three positive modes whose
relative residuals satisfy the request tolerance. The first two bending eigenvalues match an
independent 2x2 closed-form Euler-Bernoulli consistent-mass oracle within `5e-15` relative error.
Repeated execution with an empty environment
and unusable `PATH` publishes byte-identical ten-artifact directories with fallback count zero and
no Python/Node lookup.
Contract tests cover strict wire rejection, identity drift, excessive mode requests, malformed
CSR, exact symmetry, artifact self-hashes, and outer model/assembly/generated-request bindings.

Still open are general sparse/subspace extraction, geometric-stiffness assembly and linear
buckling, shell/nonlinear ModelIR graphs, a ModelIR-bound restart envelope, durable jobs and
service API, Workbench and installed distribution integration, protected-runner HIP C2,
independent broad-corpus engineering validation, and C6 decommission.
