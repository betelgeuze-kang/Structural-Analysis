# Phase 2 state-updated RC fiber beam element seed

This slice connects the state-updated reinforced-concrete fiber section to one
small-displacement, local-coordinate, two-node Euler–Bernoulli beam element.
It replaces no existing frame path and does not promote the legacy reduced-
order beam-column proxies into authoritative nonlinear evidence.

## Implemented contract

- local degrees of freedom `[u_i, v_i, theta_i, u_j, v_j, theta_j]`;
- constant axial strain and cubic-Hermite curvature interpolation;
- three Gauss integration points, each with an independently committed fiber-
  section state bound to the element and section contract hashes;
- internal force `integral(B^T [N, M] dx)` in conjugate kN/kN m units;
- a symmetric algorithmic `6 x 6` tangent
  `integral(B^T K_section B dx)` assembled from the same trial parents;
- exact agreement with the elastic Euler–Bernoulli local stiffness and the
  closed-form fixed-base tip-shear displacement, rotation, and reactions;
- zero internal force under a small-displacement rigid-body patch;
- same-parent central finite-difference verification of all six tangent
  columns in a steel-yield/concrete-damage state;
- cyclic Gauss-point state evolution with curvature reversals and nonnegative
  monotonic cumulative dissipation;
- a six-step manufactured fixed-base cantilever load/unload path with scaled
  residual and increment gates, deterministic replay, observed local quadratic
  convergence, zero fallback, and zero regularization;
- a remote initial guess that activates damped line search down to `0.125` and
  still recovers the manufactured solution;
- exact rollback of the element and every Gauss-point section state when a
  Newton step is forced to fail.

The benchmark entry point is:

```python
from structural_analysis.benchmark import (
    build_stateful_fiber_beam2d_benchmark,
)

receipt = build_stateful_fiber_beam2d_benchmark()
assert receipt["status"] == "partial"
assert receipt["contract_pass"] is True
```

`partial` means only that this isolated Level-1 element/cantilever contract
passed. It is not a broader frame or product-readiness status.

## Verification

Run the focused and neighboring regressions with:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q \
  tests/test_stateful_fiber_beam2d.py \
  tests/test_stateful_fiber_section.py \
  tests/test_beam_column_nonlinear.py \
  tests/test_authoritative_linear_frame_reference_cases.py
```

The finite-difference probe evaluates every perturbation from the identical
immutable element parent, which in turn holds the immutable parent state for
each Gauss-point section. Newton trials likewise remain uncommitted until both
scaled residual and increment gates pass.

## Claim boundary

The implementation is local-coordinate and small-displacement only. It has no
local-to-global transformation, multi-element global assembler, shear or
torsional response, geometric stiffness, corotational update, general plastic-
hinge-length model, or validated distributed-plasticity formulation. The
uniform-curvature manufactured path proves Gauss-point state transport; it is
not evidence for mesh-objective localization.

No external code-to-code, published, experimental, or customer-shadow receipt
is supplied, and no production sparse or ROCm/HIP path is connected. Full-
building equilibrium and G1 closure therefore remain false. Protected
readiness ledgers and authoritative release evidence are intentionally
unchanged.
