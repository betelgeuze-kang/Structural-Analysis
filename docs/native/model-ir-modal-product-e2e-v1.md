# ModelIR Modal Product C5 Slice

Status: bounded local CPU implementation evidence

This slice connects the existing typed Frame3D/Truss3D `ModelIR` assembly to the existing ABI
v1.9 dense modal solver. It is a bounded C5 product path for at most 128 active DOFs, with installed
static/shared run evidence at distribution v90 and a newer source-level model-bound restart. It
does not promote the generalized-eigen numerical family beyond C1 and does not claim sparse
whole-model, linear-buckling, installed restart, public/customer publication, or engineering
authority.

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

Workbench can create the exact model-bound request after running the same semantic and active
`K/M` preflight used by execution:

~~~bash
cargo run --manifest-path native/Cargo.toml -p structural-workbench -- \
  model-create-modal-analysis-request model.json \
  --case frame-modal --assembly-load-pattern LC_WEAK \
  --mode-count 3 --maximum-sweeps 4096 \
  --symmetry-relative-tolerance 1e-12 \
  --positive-semidefinite-relative-tolerance 1e-12 \
  --mode-relative-tolerance 1e-10 --cluster-relative-tolerance 1e-9 \
  --residual-relative-tolerance 1e-9 --orthogonality-tolerance 1e-9 \
  --eigensolver-relative-tolerance 1e-12 --output-dir request
~~~

The create-new directory contains canonical `analysis-request.json` and a self-hashed
`request-receipt.json`. The receipt records `execution_started=false`, the active DOF count,
source/model/request/assembly/generated-dense identities, and that the assembly selector's load
vector is not consumed by modal execution. Repeated clean-environment authoring is byte-identical;
the authored request then executes unchanged through the command below.

~~~bash
cargo run --manifest-path native/Cargo.toml -p structural-cli -- \
  analysis model-modal-run model.json request/analysis-request.json --output-dir result
~~~

The public model-bound restart reconstructs and verifies the exact model, outer request, ABI
v1.14 assembly and generated dense request before accepting the embedded ABI v1.9 phase boundary:

~~~bash
cargo run --manifest-path native/Cargo.toml -p structural-cli -- \
  analysis model-modal-resume model.json request/analysis-request.json \
  result/checkpoint.mmcp --output-dir resumed
~~~

Workbench exposes a read-only localized mode table over the complete product directory:

~~~bash
cargo run --manifest-path native/Cargo.toml -p structural-workbench -- \
  modal-result-view result --locale ko-KR --start-mode 1 --count 16
~~~

The view accepts only the exact eleven-artifact inventory, revalidates every outer receipt
artifact hash plus the strict ModelIR, outer request, assembly, generated dense request, both
checkpoints, ResultIR, ReportIR, Markdown and nested dense receipt, and then emits a self-hashed
ANSI-free table of eigenvalue, angular frequency, frequency, period, residual and dominant active
DOF amplitude. It never mutates or re-executes the result directory.

Publication is create-new and atomic. A successful directory contains:

- the canonical `model-ir.json` and `model-modal-request.json`;
- `assembly-receipt.json` and `generated-dense-request.json`;
- the dense phase boundary `checkpoint.eigcp` and outer model-bound `checkpoint.mmcp` envelope;
- self-hashed `result-ir.json`, `report-ir.json`, and deterministic `report.md`;
- the nested `dense-run-receipt.json`; and
- the outer self-hashed `run-receipt.json` binding all prior artifacts.

`checkpoint.mmcp` is a pointer-free `SAMMCP01`, aggregate-hashed envelope over the exact content,
semantic, provenance, analysis-request, assembly, generated-request and embedded dense-checkpoint identities.
Corruption, truncation, trailing bytes, or drift in any binding fails before native execution or
publication. Because the dense solve is atomic, this is an honest pre-dispatch phase restart, not
an invented mid-Jacobi state. Direct and resumed executions publish byte-identical eleven-artifact
directories.

## Verification and remaining authority

The focused product case is the repository's two-node Frame3D cantilever: C++ ABI v1.14 produces
six active DOFs, Rust adapts the exact `K/M` pair, and ABI v1.9 returns three positive modes whose
relative residuals satisfy the request tolerance. The first two bending eigenvalues match an
independent 2x2 closed-form Euler-Bernoulli consistent-mass oracle within `5e-15` relative error.
Repeated direct and model-bound resumed execution with an empty environment and unusable `PATH`
publishes byte-identical eleven-artifact directories with fallback count zero and no Python/Node
lookup. Contract tests cover strict wire rejection, identity drift, excessive mode requests,
malformed CSR, exact symmetry, artifact self-hashes, checkpoint corruption, and outer
model/request/assembly/generated-request bindings. A second load selector that produces the same
dense K/M request is still rejected, proving the outer checkpoint is not merely matrix-bound.
The append-only installed static/shared distribution v90 repeats Workbench request authoring and
the unchanged three-mode CLI execution in an empty `PATH`, binds six request/result/report
artifact identities, active DOF 6, fallback 0 and unsupported-planar rejection, and requires
Python/Node lookup 0.

Still open are general sparse/subspace extraction, geometric-stiffness assembly and linear
buckling, shell/nonlinear ModelIR graphs, durable jobs and service API, installed-distribution
exercise of the model-bound restart and `modal-result-view`, a durable modal Workbench session,
geometric mode-shape animation/participation-mass or response-spectrum visualization, local rootfs
or public/customer publication, protected-runner HIP C2, independent broad-corpus engineering
validation, and C6 decommission.
