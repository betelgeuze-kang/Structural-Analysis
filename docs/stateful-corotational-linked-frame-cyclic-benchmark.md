# Stateful corotational linked-frame cyclic benchmark

This slice connects the state-updated bilinear force-deformation link to the
actual global residual and tangent of a planar corotational fiber frame. It
keeps the pre-existing frame checkpoint schema unchanged by nesting one frame
checkpoint and one immutable state per link in a separate atomic coupling
checkpoint.

## Bounded model

The model contains two independent three-metre cantilever columns. Their free
top horizontal DOFs are connected by one global-x link, so both link endpoints
belong to active frame equations rather than to an isolated axial chain. An
`80 kN` reference horizontal load acts only on the right column. The 30 target
factors follow `0 -> +1 -> -1 -> +1`.

The link uses native kN-m force-deformation parameters:

- initial stiffness `5000 kN/m`;
- yield force `20 kN`;
- isotropic and kinematic hardening `200` and `300 kN/m`;
- algorithmic plastic tangent `454.5454545 kN/m`.

The two fiber columns deliberately use very-high-strength steel and concrete
carrier materials so they remain elastic. Their small-displacement lateral
stiffness is `910.3611111 kN/m` per column. This isolates the state and tangent
of the link while retaining the frame material and corotational geometric
tangent terms.

## Coupled equations and transaction

For link deformation `delta = u_j - u_i`, force `f(delta)`, and algorithmic
tangent `k`, the coupling layer scatters

```text
f_link,[i,j] = [-f, +f]
K_link,[i,j] = [[ k, -k],
                [-k,  k]]

f_internal   = f_frame + sum(scatter(f_link))
K_material   = K_frame,material + sum(scatter(K_link))
K_consistent = K_material + K_frame,geometric
R            = f_internal - lambda * f_reference
```

Every trial starts from one immutable mixed parent. A successful residual and
increment gate creates both the next frame checkpoint and the next link-state
tuple. A failed step returns the exact parent object and preserves the frame and
link canonical bytes and hashes.

## Verified result

The deterministic receipt records:

- 30/30 accepted targets with exact mixed and nested-frame ancestry;
- byte-identical replay, zero fallback, and zero regularization;
- link yield on the positive, negative, and final positive branches with two
  plastic-flow reversals;
- nonnegative monotonic link dissipation ending at `1.2517198603 kN m`;
- maximum free-equation residual `4.25672e-10 kN`;
- maximum link/frame force-transfer and global balance error
  `3.20828e-10 kN`, with exact link compatibility;
- elastic-prefix link-force error `3.49644e-7` against the closed-form two-column
  spring-transfer solution;
- same-parent full Jacobian finite-difference relative error `1.57291e-8`, with
  frame material, link material, and frame geometric terms all active;
- pre-roundoff minimum observed Newton order `4.20344`; the one terminal sample
  below the explicit `1e-7` relative-residual floor remains disclosed but is not
  treated as physical convergence-order evidence;
- exact rollback from a parent that already contains plastic link history.

Run the focused contract with:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q \
  tests/test_stateful_corotational_linked_frame_cyclic_benchmark.py
```

## Claim boundary

This is one dense 2D, global-axis, scalar translational link integration. It
does not support rotational or multi-axis coupling, local-axis link
transformations within this case, gap/contact, friction, uplift, viscous/rate
response, degradation, pinching, or shell connections. The separate
[fixed-reference local-axis benchmark](stateful-corotational-local-axis-linked-frame-cyclic-benchmark.md)
covers the bounded direction-cosine transformation, while the separate
[updated-current-axis benchmark](stateful-corotational-updated-axis-linked-frame-cyclic-benchmark.md)
covers one internal current-chord force and consistent link geometric tangent.
Neither broadens this global-axis case into a general link family. The columns
remain elastic, so simultaneous inelastic member-link interaction is not
validated. No external device comparison, production sparse/ROCm/HIP path,
full-building equilibrium, G1 closure, or commercial-readiness claim is made.
Protected readiness evidence and existing closure counts remain unchanged.
