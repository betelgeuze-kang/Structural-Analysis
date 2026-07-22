# Stateful corotational rotational-linked frame cyclic benchmark

This bounded internal benchmark adds one scalar relative-rotation link to the
stateful corotational fiber-frame coupling. It deliberately reuses the exact
two elastic-carrier cantilevers, geometry, right-column horizontal load, and
30-target reversal path from the global-x translational-link benchmark. Only
the link component changes: the two free top `rz` degrees of freedom are
coupled by a distinct bilinear moment-rotation material.

## Unit-safe material and assembly

The rotational material does not reuse the translational link's kN-m
force-deformation fields. Its native quantities are:

- relative rotation `theta = theta_j - theta_i` in rad;
- nodal moment in kN-m;
- initial and hardening stiffness in kN-m/rad;
- plastic and accumulated plastic rotation in rad;
- backmoment and yield moment in kN-m;
- dissipated energy in kN-m.

With `B_theta = [-1, 1]`, the physical rotational-link contribution is

```text
m_internal = B_theta^T M
K_theta = B_theta^T k_t B_theta
```

The relative-rotation map is linear, so this scalar link has no separate
force-dependent geometric tangent. Frame geometric tangent terms remain
active. The frame solver uses length-valued generalized rotation coordinates
`theta = q / L_scale`; therefore its existing `S^T K S` transformation converts
the physical kN-m/rad block to the solver's kN/m Jacobian without changing the
physical checkpoint rotations.

The checkpoint schema is version 4. Translational links retain their original
state and response types, while each rotational link requires a
`BilinearRotationalLinkState`. Mixed translational/rotational material or state
types fail closed.

## Paired elastic prefix

Each 3 m cantilever has flexural rigidity
`EI = 8193.25 kN-m^2`. For a small right-tip horizontal load `P`, two identical
cantilevers connected at their free rotations by stiffness `k_theta` transfer
the moment magnitude

```text
M = k_theta P L^2 / (2 EI + 4 k_theta L).
```

At load factor `0.1`, `P = 8 kN` and `k_theta = 5000 kN-m/rad`, the analytic
moment is `4.712874657171097 kN-m`; the corotational result is
`-4.71286483841451 kN-m`. The magnitude-relative error is
`2.083390139053011e-06`, below the `1e-5` bounded elastic-prefix tolerance.

## Cyclic result

The link uses yield moment `20 kN-m`, isotropic hardening
`200 kN-m/rad`, and kinematic hardening `300 kN-m/rad`. All 30 targets commit.
The yielded steps are
`[5, 6, 7, 8, 9, 10, 15, 16, 17, 18, 19, 20, 27, 28, 29, 30]`; negative-load
yield occurs at steps `[16, 17, 18, 19, 20]`, and two plastic-flow reversals are
observed. Final dissipated energy is `1.3957333424163187 kN-m` and is
nonnegative and monotonic.

The maximum generalized residual is `1.4214165955372948e-10 kN`; maximum
endpoint/frame moment-transfer error is `3.4567904094728874e-12 kN-m`; relative
rotation compatibility error is exactly zero. Same-parent finite differences
give relative errors `1.0366654904068796e-08` for the full frame-plus-link
Jacobian and `2.510205717953795e-10` for the moment-rotation return mapping.
The retained pre-roundoff Newton history has minimum observed order
`1.8855085667739655`.

Applying the same `0.37 rad` increment to both link endpoints produces exactly
zero relative rotation and moment. Physical rotational tangent scatter is
exact; generalized coordinate scaling differs from the analytic block by only
`2.2737367544323206e-13 kN/m`. Deterministic replay, checkpoint ancestry, and a
forced failed-step rollback are exact. Fallback and regularization counts are
zero.

## Verification

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q \
  tests/test_stateful_corotational_rotational_linked_frame_cyclic_benchmark.py
```

## Claim boundary

This is one scalar relative-`rz` link between two planar frame nodes. It is not
coupled multi-axis link response, hinge localization within a member,
gap/contact, friction, uplift, damping, rate dependence, degradation or
pinching, inelastic member/link interaction, shell or 3D connection
integration, an external device acceptance result, production sparse or
ROCm/HIP execution, full-building equilibrium, G1 closure, or commercial
readiness. Existing link/material breadth and G1 claims remain false.
