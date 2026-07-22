# Stateful corotational fixed-reference local-axis gap benchmark

## Implemented boundary

This benchmark connects a three-metre corotational fiber cantilever to a fixed
anchor with one frictionless compression-only gap. The contact normal is the
45-degree unit vector derived once from the undeformed node coordinates.

For reference normal `n0` directed from node `i` to node `j`,

```text
B     = [-n0_x, -n0_y, n0_x, n0_y]
delta = B u = n0 · (u_j - u_i)
c     = delta + g
```

The unilateral law is unchanged from the global-x gap:

```text
c >= 0: F = 0,   kt = 0       (open, including exact closure)
c <  0: F = k c, kt = k       (closed in compression)
```

The assembled link force and material tangent are `B^T F` and `B^T kt B`.
Because `n0` is fixed, the deformation Hessian and link geometric tangent are
exactly zero. Frame geometric stiffness remains active. The immutable active
bit, maximum penetration, and closure/opening counts are deterministic path
metadata; they do not add plasticity, damage, or dissipation.

## Deterministic path and checks

The reference load is `40 kN` along `n0`, the initial gap is `0.004 m`, and
the closed stiffness is `5000 kN/m`. A 30-target path produces:

- active steps `6-14` and `22-28`;
- closure transitions at steps `6` and `22`;
- opening transitions at steps `15` and `29`;
- final closure/opening counts `2/2`;
- maximum penetration `0.004830650257828986 m`;
- final recoverable contact energy exactly zero.

The small-displacement cantilever compliance predicts contact at load factor
`-0.18053192936553764`, bracketed by open `-0.15` and closed `-0.2` targets.
The open-branch deformation differs from that first-order reference by
`0.0015154200462721007` relative, below the declared `0.002` tolerance. The
linearized closed carrier-plus-gap force differs by `0.00569202668710445`,
below `0.007`. These are explicitly small-displacement reference comparisons,
not exact nonlinear frame solutions.

Same-parent finite differences report:

- open full frame-plus-gap tangent relative error
  `2.321138684755725e-08`;
- closed full frame-plus-gap tangent relative error
  `2.862327787082141e-08`;
- open material tangent error exactly zero;
- closed material tangent relative error `6.77155185258016e-12`;
- link geometric tangent exactly zero.

All 30 targets commit without fallback or regularization. Maximum residual and
global vector-balance error are both `1.2630394508050813e-09 kN`; endpoint
force transformation and scalar compatibility errors are exactly zero.
Rotating reference coordinates, displacements, forces, and tangents by
`0.371 rad` gives a maximum covariance error of
`6.821210263296962e-13`. Repeated execution is byte-identical, and a forced
Newton failure retains the active parent frame and gap checkpoint bytes.

## Focused verification

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q \
  tests/test_stateful_corotational_local_axis_gap_linked_frame_cyclic_benchmark.py
```

The tests cover 45-degree reference-normal construction, four-DOF force and
tangent scatter, degenerate/duplicate wiring rejection, active-set history,
linearized branch checks, full and material tangents, coordinate-rotation
covariance, deterministic replay, rollback, public exports, and JSON-safe
claim boundaries.

## Claim boundary

The receipt status is `partial`. It verifies one planar, frictionless, elastic,
scalar compression-only gap with a fixed-reference local normal. It does not
verify an updated/follower contact normal, friction, impact, restitution,
coupled contact, general foundation uplift, inelastic contact, member or shell
contact, three-dimensional contact, external acceptance, production
sparse/ROCm/HIP execution, full-building equilibrium, G1 closure, or
commercial readiness.
