# P2 bounded global 3D frame load path

`dense_elastic_corotational_timoshenko_frame3d_load_control.v2` scatters the
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
and nonconvergence fail closed. Every update must pass deterministic
backtracking with a strictly decreasing scaled residual. There is no
regularization or solver fallback.

The solve uses the shared source-bound 6DOF force/moment scaling. Rotational
equilibrium rows and rotation columns are scaled with the model characteristic
length before the dense solve, and the reported condition number is the exact
1-norm condition number of that scaled matrix. Scaling inputs and linear-system
values must be finite, real, and losslessly representable as binary64; coercive
boolean/string/complex sources and lossy integer conversions fail closed. Each
accepted step preserves
separate raw translational and rotational residuals/increments, the
dimensionless scaled residual and increment, and the scaling hash. The
checkpoint retains its legacy raw residual observation, while equilibrium
validation uses the scaled residual contract. A step may commit only when both
the scaled residual and scaled Newton increment gates pass, the selected line
search step is valid, the accepted state reassembles to the same equilibrium,
and the parent checkpoint remains unchanged. The convergence and line-search
histories retain these observations without turning a missing gate into a
passing value.

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
behavior. They also cover invalid increment/line-search configuration and
prove that satisfying the residual gate alone cannot commit a step.

## Claim boundary

This path is a small dense elastic verification surface. Stateful sections,
member releases/offsets/distributed loads, warping coupling, transient
dynamics, production sparse assembly, multi-turn rotation, independent
external 3D validation, verification Level 2/3, design authority, and release
readiness all remain open.
