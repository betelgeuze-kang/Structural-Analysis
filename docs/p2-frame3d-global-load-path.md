# P2 bounded global 3D frame load path

`dense_elastic_corotational_timoshenko_frame3d_load_control.v1` scatters the
energy-derived element force and tangent of the bounded corotational Frame3D
reference into one shared six-DOF-per-node space. It is an experimental
verification path, not a promoted 3D nonlinear analysis workflow.

## Bounded model contract

The v1 graph is connected and capped at 16 nodes, 32 unique members, and 60
free equations. It accepts explicit nodal reference loads, arbitrary sorted
restraint DOFs, member roll angles, and explicit Timoshenko shear areas. There
is no inferred shear factor, default support, or implicit load pattern.

## Fail-closed load control

Each strictly increasing load factor is solved by dense Newton iterations using
the same assembled internal force and tangent. Singular or over-conditioned
free tangents, non-finite corrections, principal rotation-branch violations,
and nonconvergence fail closed. There is no line search, regularization, or
solver fallback.

## Checkpoint lineage

Accepted checkpoints bind the model, solver contract, load factor, full
displacement vector, residual observation, and parent hash. A prefix run plus
resume reproduces the uninterrupted terminal checkpoint exactly. Tampered
checkpoints and cross-model resume attempts are rejected.

Terminal recovery reports support reactions and each member's global end
forces, basic deformations and forces, lengths, and strain energy.

## Focused verification

```bash
PYTHONPATH=src python3 -m pytest -q tests/test_corotational_frame3d_global.py
```

Tests cover two-member shared-DOF scatter, the cantilever
bending-plus-shear closed form with reaction recovery, two-element
free-equation equilibrium, byte-exact schema-valid resume, tamper and
cross-model rejection, and singular-support/invalid-history fail-closed
behavior.

## Claim boundary

This path is a small dense elastic verification surface. Stateful sections,
member releases/offsets/distributed loads, warping coupling, transient
dynamics, production sparse assembly, multi-turn rotation, independent
external 3D validation, verification Level 2/3, design authority, and release
readiness all remain open.
