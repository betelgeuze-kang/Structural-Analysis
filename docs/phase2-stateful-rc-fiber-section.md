# Phase 2 state-updated RC fiber section seed

This slice extends the existing one-dimensional steel-plasticity and concrete-
damage kernels into a bounded rectangular reinforced-concrete fiber section.
It adds axial-strain/curvature interaction and a section-resultant Newton solve
without promoting the result to a frame, shell, or production solver claim.

## Implemented contract

- plane-section kinematics, `epsilon_f = epsilon_0 - kappa_z y_f`;
- twelve concrete layers and aggregate top/bottom reinforcing-steel layers;
- immutable, heterogeneous per-fiber steel-plasticity and concrete-damage
  accepted states with deterministic bytes and hashes;
- axial force in kN and bending moment in kN m, using the explicit
  `1 MPa m2 = 1000 kN` conversion;
- a symmetric 2 by 2 axial-force/moment algorithmic tangent assembled from
  the exact constituent algorithmic tangents;
- same-parent central finite-difference verification in a coupled nonlinear
  steel-yield/concrete-damage state;
- cyclic curvature with two reversals, steel yielding, concrete damage, and
  nonnegative monotonic cumulative dissipation;
- scaled two-equation Newton equilibrium with line-search history, immutable
  trial parents, atomic commit, exact failed-step rollback, deterministic
  replay, zero fallback, and zero regularization;
- an intentionally remote initial guess that requires damped line-search
  factors below one and still recovers the manufactured solution;
- local residual histories with two consecutive observed convergence orders
  above `1.8` as bounded quadratic-convergence evidence;
- a six-step manufactured load/unload path whose recovered generalized-strain
  infinity-norm error is below `1e-10`.

The benchmark entry point is:

```python
from structural_analysis.materials import (
    build_stateful_rc_fiber_section_benchmark,
)

receipt = build_stateful_rc_fiber_section_benchmark()
assert receipt["status"] == "partial"
assert receipt["contract_pass"] is True
```

`partial` is deliberate: it reports success only for this isolated Level-1
section contract. The receipt remains strict-JSON serializable and explicitly
records every larger claim that is still false.

## Verification

Run the focused and neighboring regression tests with:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q \
  tests/test_stateful_fiber_section.py \
  tests/test_fiber_section.py \
  tests/test_state_updated_composite_section_newton.py \
  tests/test_state_updated_concrete_damage_newton.py \
  tests/test_state_updated_steel_material_newton.py
```

The nonlinear tangent check compares both columns of the analytic section
Jacobian against central differences evaluated from the identical immutable
committed parent state. The manufactured Newton targets stop before the
post-peak section-force map becomes non-unique, then unload from the accepted
damaged/plastic state. The separate cyclic receipt exercises the deeper
post-peak and reversal behavior without claiming uniqueness of a force-
controlled equilibrium branch there.

## Claim boundary

This is a small-strain, gross-concrete rectangular section approximation with
perfect strain compatibility. It does not implement a frame or shell element,
plastic-hinge length, distributed plasticity, shear deformation, bond slip,
confinement, multiaxial concrete, fracture-energy regularization, or mesh
objectivity. It also has no external code-to-code, published, experimental, or
customer-shadow validation and is not connected to production sparse or
ROCm/HIP execution.

Accordingly, full-building equilibrium and G1 closure remain false. Existing
product-readiness ledgers and protected evidence are intentionally unchanged;
this isolated benchmark is evidence for a narrower material-breadth advance
only.
