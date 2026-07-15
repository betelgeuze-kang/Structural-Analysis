# Engine v2 Shared Linear Frame/Truss Element Semantics v1

- Status: implemented, contract-only
- Milestone: v0.2.46 unpublished candidate
- Date: 2026-07-15
- Architecture authority: [ADR-003](adr/003-operator-abi-and-constitutive-source-policy.md)
- Roadmap authority: [Engine v2 master roadmap](structural-solver-engine-v2-master-roadmap.md)

## Purpose

The Phase 0 sparse compiler previously imported private frame/truss formulas,
local-frame construction, and semantic validation from the CPU reference
backend. The HIP symbolic assembly plan also imported the CPU backend's private
frame transform and error type. That dependency direction made the CPU backend
an accidental element-semantics owner and would have amplified drift when
offsets, releases, shells, nonlinear laws, or additional backends are added.

The v1 shared module now owns the backend-neutral linear element contract:

- linear-elastic isotropic material validation;
- Euler-Bernoulli 3D frame and axial 3D truss section compatibility;
- strict local-axis policy: global Z unless `abs(local_x_z) > 0.9`, then global Y;
- roll-aware right-handed 12-DOF global-to-local transformation;
- fixed-size FP64 12x12 frame/truss local stiffness matrices; and
- stable typed errors with code, path, and message.

The implementation is
[`elements/linear_frame_truss_v1.py`](../src/structural_analysis/engine_v2/elements/linear_frame_truss_v1.py).
It never allocates a global dense stiffness matrix. Assembly, constraint
partitioning, solver policy, result recovery, and device ownership remain in
their respective layers.

## Version and compatibility policy

The source contract and serialized compatibility identity are deliberately
separate:

```text
source semantics:
  engine-v2-linear-frame-truss-element-semantics.v1

wire/operator compatibility identity:
  engine-v2-cpu-reference-linear-static.v1
```

This milestone moves unchanged arithmetic behind a public versioned boundary;
it does not define a new numerical operator. Therefore CPU operator hashes,
ExecutionPlanV2 recovery/numeric/operator/plan hashes, fixed FGMRES registry
bindings, and downstream ResultIR bindings remain byte-for-byte unchanged.
A future semantic change must introduce a new source version and compatibility
identity instead of mutating v1.

The frozen `LC_AXIAL` regression remains:

| Artifact | SHA-256 identity |
| --- | --- |
| CPU operator | `sha256:168d0efd580683580afe44d66849c501e7e5ae6c0cc19dadce899890f5a27ca8` |
| recovery operator | `sha256:48af8d0e448dd5e0f814bd056491251132ae08d1a8d13a92ea330a0fb5908b00` |
| sparse numeric snapshot | `sha256:73aedc35e01fe2a2e5982b2646f13a2ca986a10566a889e023b7e2f1ee707658` |
| sparse plan | `sha256:ba0def8d9b29b65d387dbda87c5048df0e818939292ede8cc26ede08f566020d` |

## Consumers and dependency boundary

- The CPU reference consumes the shared public functions and keeps its old
  private names only as compatibility wrappers. Shared failures are translated
  back to the existing `cpu_reference_*` error codes.
- `ExecutionPlanV2` consumes the shared validation, transform, and stiffness
  APIs directly and no longer imports the CPU reference backend.
- The HIP assembly symbolic plan consumes the shared reference-axis/transform
  policy and no longer imports the CPU backend.
- The fixed HIP C++ v1 kernel keeps its sealed source and identity in this
  behavior-preserving slice. Its mirrored coefficients are checked against the
  shared public oracle; shared-source HIP code generation is not claimed.
- The legacy `ExecutionPlan` v1 remains intentionally CPU-backed and is outside
  this dependency fence.

## Verification

The focused suite covers independent analytic coefficients, symmetry, positive
semidefinite energy, six frame rigid-body modes, strict `0.9`/`nextafter` axis
switching, oblique roll golden bytes, malformed input fail-closed behavior,
legacy CPU error compatibility, AST dependency fences, frozen element bytes and
hashes, sparse no-global-dense assembly, and the HIP RTC shared oracle.

Observed current-source results:

- shared semantics and dependency-boundary tests: `33 passed`;
- shared/CPU/ExecutionPlan v1-v2/HIP symbolic/RTC focused set:
  `117 passed`, including the conditional native RTC shared-oracle comparison
  for both existing global-Z and added global-Y reference-axis branches;
- adjacent buffer/MGT/FGMRES registry/model-case/receipt/ResultIR set:
  `106 passed`;
- Ruff and Python byte-compilation: passed.

The current-source focused rerun executed the narrow conditional native RTC
shared-oracle regression. It is an unsigned, non-persistent, non-promoting
observation and does not issue broad or signed native parity evidence. No
performance measurement was performed, and earlier actual `gfx1030`
observations remain historical evidence for their original source snapshots.

## Claim boundary and next work

This milestone proves a versioned dependency boundary and preserved narrow
linear frame/truss behavior. It does not prove:

- shell, solid, spring, MPC, diaphragm, offset, release, or nonlinear elements;
- shared-generated HIP coefficients or broad/signed native HIP numerical parity
  beyond the narrow RTC shared-oracle regression;
- ill-conditioned/slender-model scaling or iterative refinement;
- nonlinear/dynamic/buckling/modal/time-history analysis;
- peak RSS, end-to-end O(N), solver speedup, or commercial readiness; or
- independent V&V against MIDAS, ETABS, OpenSees, or design-code benchmarks.

The next numerical slice should add scaling/refinement gates for slender and
ill-conditioned models without changing this v1 element identity. The next
element-breadth slice should add offsets/releases and a shell CPU patch suite on
top of the shared boundary before extending HIP code generation.
