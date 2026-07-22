# Fixed-reference local-axis linked-frame cyclic benchmark

This bounded benchmark connects the free top of one planar corotational fiber
cantilever to a fixed anchor with a 45-degree bilinear link. Its purpose is to
verify the reference-axis transformation between one scalar force-deformation
state and four global translational frame DOFs. It does not turn the link into
an updated corotational or follower element.

## Geometry and loading

- fixed anchor: `(0, 0)`;
- fixed column base: `(3, 0)`;
- free column top: `(3, 3)`;
- one 3 m corotational fiber column between the base and top;
- one `local_axial` link from the anchor to the top;
- reference direction `n = (1/sqrt(2), 1/sqrt(2))`;
- 80 kN reference load applied at the top along `n`;
- 30 targets tracing `0 -> +1 -> -1 -> +1`, with a 0.02 first target used
  only for the small-displacement analytic prefix.

The fiber section is deliberately kept elastic. Link stiffness is
`5000 kN/m`, yield force is `20 kN`, and isotropic/kinematic hardening are
`200/300 kN/m`. This isolates transformation and link-state behavior while the
frame material and corotational geometric tangent terms remain active.

## Fixed-reference transformation

For undeformed endpoints `X_i` and `X_j`, the implementation computes

```text
n = (X_j - X_i) / ||X_j - X_i||
B = [-n_x, -n_y, n_x, n_y]
d = B u_link
f_link_global = B^T q(d)
K_link_global = B^T k_t(d) B
```

The same immutable accepted parent supplies the frame element states and the
bilinear link state. A successful Newton target creates the next nested frame
checkpoint and link state together. A failed target returns the exact parent
bytes and hashes.

The axis is fixed to the undeformed coordinates. No current-chord update or
additional link geometric stiffness is included.

## Verification gates

The public receipt checks:

- 30/30 atomic commits, exact ancestry, and byte-exact deterministic replay;
- equal-and-opposite two-dimensional endpoint forces and zero transverse force
  leakage;
- four-DOF off-axis material tangent scatter and global vector equilibrium;
- a small-displacement compliance solution with relative force error below
  `1e-4`;
- positive and negative yielding, two plastic-flow reversals, monotonic
  nonnegative dissipation, and positive final dissipated energy;
- a same-parent finite-difference check with frame material, link material, and
  frame geometric tangent terms all active;
- pre-roundoff full-step Newton order and zero fallback/regularization;
- exact rollback from a parent that already contains plastic link history.

The current deterministic receipt reports a maximum force-transformation error
of about `7.11e-15 kN`, link compatibility error below `1e-12 m`, maximum
residual/vector-balance error of about `1.22e-9 kN`, mixed tangent relative
error of about `3.91e-8`, and final link dissipated energy of about
`1.767 kN m`.

Run the global, fixed-reference, and updated-axis link contracts with:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q \
  tests/test_stateful_corotational_local_axis_linked_frame_cyclic_benchmark.py \
  tests/test_stateful_corotational_updated_axis_linked_frame_cyclic_benchmark.py \
  tests/test_stateful_corotational_linked_frame_cyclic_benchmark.py
```

## Claim boundary

This is one dense 2D scalar translational link with a fixed reference local
axis. This case itself does not update that axis; the separate
[updated-current-axis benchmark](stateful-corotational-updated-axis-linked-frame-cyclic-benchmark.md)
covers one internal axial current-chord formulation. General nonconservative
follower external loads, rotational links, coupled multi-axis constitutive
response, gap/contact, friction, uplift, viscous/rate response, degradation,
pinching, shell connections, and simultaneous inelastic frame-member/link
interaction remain open. No external device acceptance, production sparse or
ROCm/HIP path, full-building equilibrium, G1 closure, or commercial-readiness
claim is made. Protected readiness evidence and existing closure counts remain
unchanged.
