# ModelIR Frame3D Linear-Buckling Product C5 Slice

Status: bounded source-built plus installed static/shared CPU implementation and verification evidence

This slice composes the existing typed ModelIR linear-static path, ABI v1.15 prestress
geometric-stiffness assembly, and ABI v1.9 dense generalized-eigen solver into one strict
product. It is limited to Frame3D graphs with one nodal reference-load pattern and at most 128
active DOFs. Append-only installed static/shared distribution v98 and local rootfs diagnostic v20
repeat the exact author, run, resume, localized read-only view and durable Workbench path in an
empty PATH; v20 additionally verifies UID/GID 65532, read-only root/payload, writable workspace and
loopback-only isolation. This is not external validation, engineering acceptance, customer
publication, release authority, or broad PM-1 closure.

## Exact derivation

`structural-model-ir-linear-buckling-analysis-request.v1` binds the ModelIR content, semantic and
provenance identities, one CPU case, the reference load pattern, exact PCG controls, and exact
dense spectral controls. Execution then:

1. constructs the model-bound linear-static reference request;
2. assembles and solves the exact active equilibrium with the real PCG checkpoint;
3. verifies typed global/element recovery and constrained reactions;
4. supplies that exact full equilibrium displacement to ABI v1.15;
5. independently verifies active-map, canonical CSR, topology and compressed-frame ordering for
   elastic `K` and geometric `Kg`;
6. deterministically densifies the symmetric operators and solves `K phi = lambda Kg phi`; and
7. publishes a strict ResultIR, ReportIR, deterministic Markdown, nested receipts and checkpoints.

The combined assembly receipt hashes `K`, `Kg`, the equilibrium displacement, frame-compression
vector, reference ResultIR and recovery. Fallback is required to be zero throughout.

## Public commands

Workbench authors a request only after executing the complete path as a non-publishing preflight:

```text
structural-workbench model-create-buckling-analysis-request MODEL.json \
  --case FRAME-BUCKLING --reference-load-pattern LC_AXIAL \
  --max-iterations 64 --absolute-residual-tolerance 1e-12 \
  --relative-residual-tolerance 1e-12 --maximum-increment 0 \
  --mode-count 2 --maximum-sweeps 4096 \
  --symmetry-relative-tolerance 1e-12 \
  --positive-semidefinite-relative-tolerance 1e-12 \
  --mode-relative-tolerance 1e-10 --cluster-relative-tolerance 1e-9 \
  --residual-relative-tolerance 1e-9 --orthogonality-tolerance 1e-9 \
  --eigensolver-relative-tolerance 1e-12 --output-dir REQUEST
```

The receipt records the generated reference request, both assembly identities, generated dense
request, active DOF count, critical factor, all three preflight markers, and
`product_publication_started=false`.

Direct and restarted products use:

```text
structural-cli analysis model-buckling-run MODEL.json REQUEST/analysis-request.json \
  --output-dir RESULT

structural-cli analysis model-buckling-resume MODEL.json REQUEST/analysis-request.json \
  RESULT/checkpoint.mbcp --output-dir RESUMED
```

Each successful directory contains exactly eighteen artifacts: the exact model and outer request;
generated reference request; reference assembly, PCG checkpoint, outer linear checkpoint,
ResultIR, recovery and reaction; buckling assembly and generated dense request; dense and aggregate
checkpoints; dense receipt; final ResultIR, ReportIR, Markdown and outer run receipt. Direct,
repeated and resumed directories are byte-identical.

The read-only localized view revalidates that full inventory before rendering:

```text
structural-workbench buckling-result-view RESULT --locale ko-KR --start-mode 1 --count 16
```

It emits a self-hashed factor table containing load factor, relative residual, generalized `K`,
generalized `Kg`, and dominant active-DOF amplitude. It does not modify or re-execute the result.

## Durable Workbench

The dedicated profile has only imported, validated, direct, resumed and reported stages:

```text
structural-workbench workflow-model-buckling MODEL.json REQUEST/analysis-request.json \
  --workspace BUCKLING-WORKBENCH
```

The restartable surface is `import-model-buckling`, `buckling-validate`, `buckling-run`,
`buckling-resume`, `buckling-report`, `buckling-status`, and `buckling-inspect`. Validation reruns
the full non-publishing preflight. Resume publishes `04-resume` only after all eighteen files match
`03-run` byte for byte. Reopen verifies every existing stage, reconciles an atomically published
stage ahead of the session file, and rejects gaps, an unexpected comparison stage, identity drift,
checkpoint corruption or inventory drift. Reporting publishes deterministic English and Korean
views and records external comparison and engineering verdict as explicit null values.

## Checkpoint and verification

`checkpoint.mbcp` is the pointer-free little-endian `SAMBKP01` envelope. It binds ten identities:
the ModelIR triple, outer analysis request, generated reference request, reference assembly,
buckling assembly, generated spectral request, reference ResultIR and reference recovery. It also
hashes and embeds the exact model-bound PCG checkpoint and dense spectral checkpoint. Truncation,
trailing bytes, every single-byte mutation, and drift in any of the ten bindings fail with the
checkpoint-mismatch taxonomy before publication.

The focused two-node compressed cantilever has six active DOFs. Its two bending factors match an
independent 2x2 Euler-Bernoulli cantilever generalized-eigen oracle within `5e-14` relative error;
reference displacement, axial compression and equilibrium residual are independently checked.
Clean-environment tests use an unusable `PATH`, require Python/Node lookup zero, fallback zero,
source nonmutation, localized deterministic views, durable reopen at every stage and exact
direct/restart artifact equality.

## Fail-closed and remaining boundary

The current path rejects member loads, self-weight, nonzero prescribed supports, Truss3D, mixed
tension/compression or no-compression states, non-equilibrium reference state, malformed CSR,
identity drift, fallback, and unsupported mode/control sizes. Installed distribution v98 binds the
two-mode/six-active-DOF compressed cantilever, exact eighteen-artifact repeat/restart parity,
repeated en-US/ko-KR views, source nonmutation, invalid-window rejection, staged/one-shot durable-
session identity, crash reconciliation, checkpoint-tamper rejection, explicit null authority
boundaries and twelve distinct identities for both static and shared CPU bundles. Local rootfs
diagnostic v20 repeats those exact boundaries under the isolated installed runtime and freezes
v1-v19 at their narrower authority. Sparse or large-mode extraction, shell/general stability,
follower/distributed prestress, nonlinear buckling, imperfections, path-following, installed/rootfs
evidence for the separately source-built durable job/service profile, protected-runner
HIP C2, independent broad-corpus/code-to-code validation, engineering acceptance, customer image
publication, release authority and C6 remain open.
