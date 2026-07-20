# Phase 2 stateful fiber-frame global assembly seed

This slice connects the local stateful fiber beam to a bounded
small-displacement 2D frame assembly. It adds fixed initial-chord coordinate
transformation, dense multi-member force/tangent assembly, and an immutable
committed checkpoint that binds global displacements and every member's
integration-point state to an explicit parent hash and epoch.

## Implemented contract

- physical nodal degrees of freedom `[ux, uy, theta]` and a length-scaled
  rotation coordinate for the dense Newton solve;
- fixed initial-chord `6 x 6` global-to-local transformations with conjugate
  force and tangent mappings;
- a structural `AxialCurvatureSection` protocol, demonstrated by the RC fiber
  section without an exact-class dependency in the beam kernel;
- dense global internal-load and consistent-tangent assembly for two members;
- exact element-response binding to each committed element parent and exact
  section-response binding to every committed Gauss-point parent;
- committed checkpoints carrying `parent_state_hash`, `epoch`, global physical
  displacements, and all member/integration-point states;
- a 4 MiB-bounded, signed-zero-preserving canonical UTF-8 JSON artifact with a
  closed JSON Schema for the built-in RC fiber state hierarchy;
- fail-closed duplicate-key, non-finite-token, noncanonical-byte, unknown-field,
  nested-state-hash, problem-contract, and existing-target checks;
- exact persisted checkpoint restoration and continuation to the same final
  checkpoint as the uninterrupted nonlinear load path;
- a separate 32 MiB/256-checkpoint ancestor-chain envelope rooted at the exact
  epoch-zero problem state, with contiguous epoch/step indices, exact parent
  links, terminal identity, and a domain-separated chain hash;
- exact persisted chain restoration and continuation from its terminal
  checkpoint to the same final state as the uninterrupted nonlinear path;
- residual-and-increment-gated Newton commit, exact failed-step rollback,
  deterministic replay, and exact in-memory checkpoint restart;
- a two-element elastic cantilever closed-form check, arbitrary rigid rotation
  invariance, all-column global tangent finite differences, and a nonlinear
  non-collinear two-member L-frame path.

The benchmark entry point is:

```python
from structural_analysis.benchmark import (
    build_stateful_fiber_frame2d_benchmark,
)

receipt = build_stateful_fiber_frame2d_benchmark()
assert receipt["status"] == "partial"
assert receipt["contract_pass"] is True
```

`partial` means only that this bounded Level-1 analytic/manufactured contract
passed. It is not a general frame solver or product-readiness status.

## Persisted checkpoint artifact

The artifact writer validates one accepted checkpoint against the explicit
problem and creates a new file without overwriting an existing target. The
reader checks the byte limit and canonical JSON form, validates every
closed-schema object, reconstructs the steel/concrete fiber states, verifies all
nested state hashes, and finally re-runs the frame checkpoint validator against
the supplied problem. The single-checkpoint artifact retains its
`parent_state_hash` without pretending that the referenced parent is present.

```python
from structural_analysis.assembly import (
    read_stateful_fiber_frame2d_checkpoint_artifact,
    write_stateful_fiber_frame2d_checkpoint_artifact,
)

write_stateful_fiber_frame2d_checkpoint_artifact(
    problem,
    accepted_checkpoint,
    "accepted-checkpoint.json",
)
restored = read_stateful_fiber_frame2d_checkpoint_artifact(
    problem,
    "accepted-checkpoint.json",
)
assert restored.state_hash == accepted_checkpoint.state_hash
assert restored.canonical_bytes() == accepted_checkpoint.canonical_bytes()
```

For a complete history, the chain writer accepts only an exact epoch-zero root
followed by contiguous checkpoints whose `parent_state_hash` equals the
preceding checkpoint's `state_hash`. Missing prefixes, removed or reordered
epochs, mixed problem contracts, wrong terminal metadata, and chain-hash
tampering fail closed.

```python
from structural_analysis.assembly import (
    make_stateful_fiber_frame2d_checkpoint_chain,
    read_stateful_fiber_frame2d_checkpoint_chain_artifact,
    write_stateful_fiber_frame2d_checkpoint_chain_artifact,
)

chain = make_stateful_fiber_frame2d_checkpoint_chain(
    problem,
    (initial_checkpoint, *accepted_checkpoints),
)
write_stateful_fiber_frame2d_checkpoint_chain_artifact(
    problem,
    chain,
    "accepted-checkpoint-chain.json",
)
restored_chain = read_stateful_fiber_frame2d_checkpoint_chain_artifact(
    problem,
    "accepted-checkpoint-chain.json",
)
assert restored_chain.chain_hash == chain.chain_hash
assert restored_chain.terminal_checkpoint.state_hash == chain.terminal_checkpoint.state_hash
```

The exact checkpoint codec remains the only restart representation for this
bounded solver. A separate direct-module adapter can project each checkpoint's
ordered `member -> Gauss point -> fiber` material bytes into the Engine v2
`MaterialStateBundle` lifecycle without replacing or mutating the checkpoint:

```python
from structural_analysis.assembly.stateful_fiber_frame2d_material_state_bundle import (
    adapt_stateful_fiber_frame2d_checkpoint_to_material_state_bundle,
    create_initial_stateful_fiber_frame2d_material_state_bundle,
)

accepted_bundle = create_initial_stateful_fiber_frame2d_material_state_bundle(
    problem,
    initial_checkpoint,
    model_ir_content_hash=model_ir.content_hash,
    execution_plan_hash=plan.plan_hash,
    solver_state_hash=initial_state.state_hash,
)
transition = adapt_stateful_fiber_frame2d_checkpoint_to_material_state_bundle(
    problem,
    initial_checkpoint,
    accepted_checkpoint,
    accepted_bundle,
    trial_solver_state_hash=trial_state.state_hash,
    committed_solver_state_hash=committed_state.state_hash,
)
accepted_bundle = transition.committed_bundle
```

Generated stable entry identities bind exact member, section, integration-point,
fiber, material-type, and material-schema order. Each entry retains the existing
steel or concrete canonical binary state bytes. The bundle ID includes the full
checkpoint state digest, while the bundle contract binds the caller-supplied
ModelIR, ExecutionPlan, and solver StateIR hashes. The adapter validates those
exact hash values but cannot prove that a caller-supplied ModelIR is semantically
equivalent to the bounded frame problem.

The serialized artifact uses the
`canonical-signed-zero-preserving-utf8-json.v1` storage profile. Preserving the
sign of binary64 zero is required because the immutable checkpoint hash is
defined over exact little-endian binary state bytes.

## Verification

Run the focused and neighboring regressions with:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q \
  tests/test_stateful_fiber_frame2d.py \
  tests/test_stateful_fiber_beam2d.py \
  tests/test_stateful_fiber_section.py \
  tests/test_authoritative_linear_frame_reference_cases.py
```

The finite-difference probe evaluates every free-equation column from the same
immutable frame checkpoint. A successful load step creates exactly one new
epoch whose parent hash is the accepted checkpoint; a failed step returns the
identical parent object and canonical bytes.

## Claim boundary

The transformation is fixed to the initial chord, so this remains a
small-displacement material-nonlinear reference. It has no corotational update,
geometric stiffness, shear deformation, torsion, general model import,
prescribed-displacement surface, generalized section-state codec registry, or
production sparse solver. Persistent single-checkpoint and complete-chain
restoration are limited to the built-in RC section state hierarchy represented
by combined-hardening steel and asymmetric concrete-damage fiber states. The
chain is state/restart transport; reading it does not replay or independently
prove every constitutive transition. Partial-prefix chain bundles and a
generalized material/section codec registry remain unsupported. The one-way
MaterialStateBundle projection cannot reconstruct global displacements, restore
a checkpoint, prove convergence or constitutive evolution, or grant numerical,
engineering, release, or commercial authority. The two-member Gauss-point state
path is not evidence for plastic-hinge calibration,
localization regularization, or mesh-objective distributed plasticity.

No external code-to-code, published, experimental, or customer-shadow receipt
is supplied. Production ROCm/HIP execution, full-building equilibrium, and G1
closure remain false. Protected readiness ledgers and authoritative release
evidence are intentionally unchanged.
