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
prescribed-displacement surface, persistent checkpoint parser, or production
sparse solver. The two-member Gauss-point state path is not evidence for
plastic-hinge calibration, localization regularization, or mesh-objective
distributed plasticity.

No external code-to-code, published, experimental, or customer-shadow receipt
is supplied. Production ROCm/HIP execution, full-building equilibrium, and G1
closure remain false. Protected readiness ledgers and authoritative release
evidence are intentionally unchanged.
