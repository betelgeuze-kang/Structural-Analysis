# Phase 2 stateful material-geometric truss arc-length path

## Outcome

This increment connects the bounded two-bar material-geometric truss to the
existing multi-DOF spherical arc-length kernel. Each physical attempt is bound
to one immutable accepted material parent. Displacement, load factor, and both
integration-point states commit only after equilibrium and arc-constraint
gates pass.

The deterministic default run reports:

- 2 free apex equations and 2 committed material states;
- 12 accepted physical steps and 1 rejected step;
- automatic arc reduction from `0.008 m` to `0.004 m` after the rejection;
- exact accepted-state rollback at that failed boundary;
- 117 dense state-tangent solves with zero fallback and zero regularization;
- `1.1070540040236665e-09 kN` maximum accepted residual infinity norm;
- `2.6813788480697064e-13 m2` maximum accepted spherical-constraint error;
- a sampled maximum load factor of `0.9523764071492837`;
- a final load factor of `0.9047160186128145` at
  `-0.050492519708786654 m` vertical displacement;
- 11 accepted material-state changes and
  `1.7477601986809785 MJ/m3` final dissipated energy density;
- exact deterministic replay; and
- a bit-identical final checkpoint after restart from the rejected-step
  boundary.

The receipt returns `status=partial` with `contract_pass=true`. `partial` is
intentional: this remains a Level-1, two-element verification path.

## Transactional path bridge

The reusable vector kernel operates on local increments for one attempt:

```text
u_actual      = u_accepted + delta_u
lambda_actual = lambda_accepted + delta_lambda
R             = F_internal(u_actual, accepted_material_state)
                - lambda_actual * F_reference
```

For every residual, correction, and tangent action in that attempt, the
material integration begins from the same accepted parent. The local kernel
therefore cannot mutate durable constitutive state while iterating.

When both gates pass, the bridge commits atomically:

```text
(u, lambda, material_state_left, material_state_right)
```

When an attempt fails, the bridge retains the same accepted-state object,
canonical structural bytes, and both material-state byte strings, then reduces
the arc length. The checkpoint hash binds the accepted state hash, path
contract, current arc length, prior tangent orientation, attempt count, and
last outcome.

## Tangent and solver boundary

The element tangent remains

```text
K_consistent = K_material + K_geometric
K_material   = A Et / L0 * (n outer n)
K_geometric  = N / l * (I - n outer n)
```

The arc bridge exposes this as a state-tangent action. The verification solver
materializes exactly one dense `2 x 2` tangent and solves it with NumPy. The
vector kernel independently recomputes the action residual for every returned
solution.

This dense path is deliberate. It does not support a sparse, matrix-free,
production, or GPU claim.

An arc-local central-difference check from one immutable material parent gives:

- displacement Jacobian relative error `4.480813124277594e-10`; and
- negative load-derivative relative error `3.9312908484134823e-10`.

## Independent analytic branch

For monotonic symmetric compression, the reference curve is evaluated without
calling the material return-mapping implementation. It uses the material
parameter values in a closed-form piecewise bilinear law:

```text
sigma = E epsilon                         before yield
sigma = fy + Et (epsilon - fy/E)          after yield
P     = 2 A sigma h_current / l_current
```

Together with exact current-chord geometry, this produces an analytic limit
point at:

```text
vertical displacement = -0.015179934566880651 m
load factor           =  0.952395478327033
```

The accepted arc path brackets that displacement between steps 3 and 4,
changes the sign of the vertical consistent tangent, and continues onto the
descending load branch. Across all accepted points, the maximum load-factor
difference from the analytic curve is `1.1070477867747286e-11`. The discrete
sampled maximum lies `1.9071177749241386e-05` below the continuous analytic
maximum.

This is independent structural and constitutive algebra using shared parameter
values. It is Level-1 analytic evidence, not code-to-code evidence.

## Verification inventory

- same-parent displacement and load linearization finite differences;
- explicit residual check for every dense tangent solve;
- equilibrium and spherical-constraint commit gates;
- exact failed-attempt rollback and step-size reduction;
- monotonic downward displacement orientation;
- interior maximum load and descending branch;
- vertical tangent sign change around the analytic limit point;
- material and geometric tangent terms active at every committed step;
- monotonic material-state commits and positive dissipation;
- deterministic full replay;
- restart from a rejected-step checkpoint; and
- JSON-safe receipt serialization, including explicit `null` for an
  inapplicable rejected-attempt maximum metric.

## Files

- `src/structural_analysis/benchmark/material_geometric_truss_arc_length.py`
- `tests/test_material_geometric_truss_arc_length.py`

## Claim boundary

The receipt supports only these bounded claims:

- stateful material-geometric arc-length for one symmetric planar two-bar
  truss;
- passage through its analytic limit point onto a descending branch;
- adaptive failed-step rollback;
- deterministic in-memory checkpoint restart; and
- agreement with the disclosed closed-form monotonic curve.

It does **not** establish:

- a general 2D/3D truss, frame, or shell formulation;
- finite-strain constitutive behavior;
- a durable serialized checkpoint artifact;
- external code-to-code, published, experimental, or customer-shadow
  validation;
- production sparse, matrix-free, or ROCm/HIP execution;
- full-building material-geometric equilibrium; or
- G1 closure.

These limitations remain explicit false claims and blockers in the receipt.
