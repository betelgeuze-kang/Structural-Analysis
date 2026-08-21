# ModelIR Modal Product C5 Slice

Status: bounded local CPU implementation evidence

This slice connects the existing typed Frame3D/Truss3D `ModelIR` assembly to the existing ABI
v1.9 dense modal solver. It is a bounded C5 product path for at most 128 active DOFs, with installed
static/shared run, model-bound restart and read-only result-view evidence at distribution v91. It
does not promote the generalized-eigen numerical family beyond C1 and does not claim sparse
whole-model, linear-buckling, public/customer publication, or engineering
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
cyclic-Jacobi path. Linear buckling is owned by a separate source-built product that constructs a
load-dependent geometric stiffness matrix from an exact reference equilibrium; it does not
broaden this modal path's authority.

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

## Durable Workbench flow

The source-level Workbench now owns a separate modal-only durable session. It deliberately does
not reuse the linear Workbench's mandatory external-comparison and human-review stages. A complete
local flow is:

~~~bash
cargo run --manifest-path native/Cargo.toml -p structural-workbench -- \
  workflow-model-modal model.json request/analysis-request.json --workspace modal-workbench
~~~

The equivalent restartable commands are `import-model-modal`, `modal-validate`, `modal-run`,
`modal-resume`, and `modal-report`; `modal-status` and `modal-inspect` reopen and re-verify the
durable state. The stage chain is exactly imported, validated, direct, resumed, and reported.
Validation reconstructs the ABI v1.14 assembly identities. Direct execution publishes the full
eleven-artifact ABI v1.9 product in `03-run`. Resume reconstructs from `checkpoint.mmcp` into a
temporary directory and publishes `04-resume` only after all eleven direct/resumed files are byte
identical. A session file that lags an already atomic stage is reconciled on reopen; gaps,
unexpected comparison stages, identity drift, checkpoint corruption, product inventory drift, and
even a semantically altered but re-self-hashed validation receipt fail closed.

The report stage re-verifies the resumed product and atomically publishes deterministic,
self-hashed `en-US` and `ko-KR` mode tables. Its receipt records external comparison and engineering
verdict as explicit null values. This is a source-level C5 operator workflow, not external parity
or engineering acceptance. The currently required installed v91 and rootfs v13 receipts exercise
the same author/run/resume/view product pieces as discrete commands, but do not yet claim installed
durable-session authority.

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
The append-only installed static/shared distribution v91 retains the v90 Workbench request
authoring and unchanged three-mode CLI execution, then resumes from the exact model-bound
checkpoint and requires byte-identical eleven-artifact direct/resumed output. It repeatedly runs
the self-hashed en-US/ko-KR mode-table view in an empty `PATH`, proves source nonmutation and
invalid-window rejection, and requires Python/Node lookup 0 and fallback 0.
The append-only local rootfs diagnostic v13 executes the same installed author/run/resume/view
surface as UID/GID 65532 with an empty `PATH`, read-only root and payload, writable workspace and
loopback-only networking. The installer independently binds its own bundle manifest plus
`structural-cli`, exact request and eleven-artifact result inventories, strict three-mode CPU
ResultIR, completed run receipt, byte-identical direct/resumed directory and stdout, repeated
self-hashed localized views, source-directory nonmutation and invalid-window rejection. This is
local diagnostic C5 evidence, not a customer image, engineering verdict or release receipt.

Still open are general sparse/subspace extraction, shell/nonlinear ModelIR graphs, durable jobs
and service API, installed durable modal
Workbench-session authority, geometric mode-shape animation/participation-mass or response-spectrum visualization,
customer-image or public/customer publication, protected-runner HIP C2, independent broad-corpus
engineering validation, and C6 decommission.
