# Fiber-frame physical force/moment scaling and residual trace

## Purpose

PR-J1 freezes the bounded fiber-frame topology and the solver-coordinate
transformation used to express rotations as length-like generalized unknowns.
That transformation does not solve the mixed-unit convergence problem:

```text
translation residual  kN
rotation residual     kN m
```

A single raw vector norm over those quantities has no stable physical meaning.
PR-J2 introduces a separate physical scaling receipt and residual trace while
preserving the current Newton solver and all result-authority boundaries.

## Characteristic length

The v1 profile derives one deterministic length from source geometry:

```text
Lchar = diagonal length of the XY node-coordinate bounding box
```

The receipt stores `characteristic_length_source_hash`, binding:

- the J1 node-coordinate byte hash;
- X and Y extents;
- the resulting characteristic length;
- the profile `node_coordinate_bbox_diagonal.v1`.

A different geometry therefore creates a different physical scaling identity.

## Force and moment references

From the J1 six-DOF reference-load vector:

```text
Fref = max(
  max absolute UX/UY reference force,
  max absolute RZ reference moment / Lchar,
  1 kN
)

Mref = Fref * Lchar
```

The per-node physical scaling block is:

```text
[1/Fref, 1/Fref, 0, 0, 0, 1/Mref]
```

Inactive UZ/RX/RY equations intentionally receive zero scaling and cannot
participate in the residual trace.

This is distinct from the J1 solver-coordinate map:

```text
J1  q_generalized <-> [UX_m, UY_m, RZ_rad]
J2  [force_kN, force_kN, moment_kN_m] -> dimensionless residual
```

## Residual trace

For one exact `StatefulFiberFrame2DAssembly`, the trace binds:

- problem contract and J1 topology-plan hash;
- J2 physical scaling hash;
- parent checkpoint hash;
- target load factor;
- canonical assembly hash;
- full physical six-DOF residual bytes;
- physical residual in current solver order;
- generalized free-equation residual emitted by the existing solver;
- dimensionless scaled free residual;
- raw translational `Linf` in kN;
- raw rotational `Linf` in kN m;
- scaled `Linf` and `L2`;
- governing physical equation, node, and component.

The trace independently verifies:

```text
r_physical_solver = F_internal - F_external
r_generalized_free = S_coordinate * r_physical_free
r_scaled_free = D_physical * r_physical_free
```

## Authority boundary

The receipt and trace are observation/compiler artifacts. They do not declare
that the Newton iteration converged. They grant no:

- nonlinear numerical-result authority;
- displacement authority;
- material-state authority;
- reaction/member-force/fiber-output authority;
- design/code authority;
- release or commercial authority.

PR-J3 will bind checkpoint ancestry to a typed nonlinear kinematic-state chain.
PR-J4 will join that chain with the merged material-state projection chain.
Only a later terminal gate and NonlinearResultIR adapter may promote a committed
numerical state.

## Focused validation

```bash
PYTHONPATH=src python -m pytest -q \
  tests/test_stateful_fiber_frame2d_execution_topology.py \
  tests/test_stateful_fiber_frame2d_physical_scaling.py \
  tests/test_stateful_fiber_frame2d.py
```
