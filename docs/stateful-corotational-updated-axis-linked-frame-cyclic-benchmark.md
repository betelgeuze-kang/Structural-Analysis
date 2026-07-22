# Updated-current-axis linked-frame cyclic benchmark

This bounded benchmark connects the free top of one planar corotational fiber
cantilever to a fixed anchor with a 45-degree bilinear axial link. Unlike the
paired fixed-reference case, this link measures its deformation from the
current endpoint distance and rotates its internal force direction with the
current chord.

## Geometry and loading

- fixed anchor: `(0, 0)`;
- fixed column base: `(3, 0)`;
- free column top: `(3, 3)`;
- one 3 m corotational fiber column between the base and top;
- one `updated_axial` link from the anchor to the top;
- reference length `3 sqrt(2) m` and initial direction
  `(1/sqrt(2), 1/sqrt(2))`;
- 80 kN reference load applied at the top along the initial link direction;
- 30 targets tracing `0 -> +1 -> -1 -> +1`, with a `0.02` first target for
  the first-order elastic prefix.

The carrier section stays elastic. Link stiffness is `5000 kN/m`, yield force
is `20 kN`, and isotropic/kinematic hardening are `200/300 kN/m`. The paired
fixed-reference problem uses the same carrier, material parameters, loading,
and targets so the axis-update effect is isolated.

## Current-chord equations

For undeformed endpoints `X_i`, `X_j` and translations `u_i`, `u_j`, define

```text
r = (X_j + u_j) - (X_i + u_i)
L = ||r||
L0 = ||X_j - X_i||
n = r / L
e = L - L0
B = [-n_x, -n_y, n_x, n_y]
P = I - n n^T
H = (1/L) [[P, -P], [-P, P]]
```

The scalar bilinear material returns force `q(e)` and same-parent algorithmic
tangent `k_t`. The assembled link terms are

```text
f_link = B^T q
K_link_material = B^T k_t B
K_link_geometric = q H
K_link_consistent = K_link_material + K_link_geometric
```

The implementation rejects a collapsed current chord. It also rejects a
fixed-reference and updated-current-axis link that produce the same zero-state
global kinematic row, preventing accidental duplicate physical wiring.

## Verification gates

The public receipt checks:

- exact zero deformation under a finite rigid rotation plus translation and
  the correctly rotated current direction;
- exact stretched-length deformation and a finite-difference check of `H`;
- 30/30 atomic frame/link commits, exact ancestry, byte-exact replay, and exact
  rollback from a parent containing plastic link history;
- current-axis force projection, zero transverse leakage, endpoint balance,
  top-node equilibrium, and global vector balance;
- positive and negative yielding, two plastic-flow reversals, monotonic
  nonnegative dissipation, and positive final dissipated energy;
- positive- and negative-force yielded same-parent finite-difference Jacobians
  with frame material, link material, frame geometric, and link geometric terms
  all active;
- pre-roundoff full-step Newton convergence, zero fallback, and zero
  regularization;
- a nonzero difference from the paired fixed-reference solution.

The deterministic receipt currently reports maximum current-axis rotation
`0.0062572 rad`, maximum link geometric-tangent infinity norm
`19.549 kN/m`, maximum updated-versus-fixed link-force difference
`0.11875 kN`, full mixed-tangent relative error `9.23e-9`, maximum
residual/vector-balance error `6.86e-11 kN`, and zero measured length
compatibility error. Final link dissipated energy is about `1.767 kN m`.

Run the global, fixed-reference, and updated-axis link contracts with:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q \
  tests/test_stateful_corotational_linked_frame_cyclic_benchmark.py \
  tests/test_stateful_corotational_local_axis_linked_frame_cyclic_benchmark.py \
  tests/test_stateful_corotational_updated_axis_linked_frame_cyclic_benchmark.py \
  tests/test_stateful_corotational_rotational_linked_frame_cyclic_benchmark.py
```

## Claim boundary

This is one dense 2D internal scalar axial link whose force follows its current
chord. It is not a general nonconservative follower external-load formulation.
Coupled multi-axis constitutive response, gap/contact, friction, uplift,
viscous/rate response, degradation, pinching, shell connections, and
simultaneous inelastic frame-member/link interaction remain open. A separate
[scalar rotational-link benchmark](stateful-corotational-rotational-linked-frame-cyclic-benchmark.md)
covers one relative-`rz` moment-rotation link only and is not multi-axis
connection breadth. No external device acceptance, production sparse or
ROCm/HIP path,
full-building equilibrium, G1 closure, or commercial-readiness claim is made.
Protected readiness closure counts remain unchanged.
