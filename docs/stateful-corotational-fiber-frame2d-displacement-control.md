# Stateful Corotational Frame2D Direct Displacement Control

The internal
`dense-augmented-consistent-direct-displacement-control.v1` profile controls one
free translational `UX` or `UY` degree of freedom while solving the proportional
load factor as an additional unknown. It is intended for monotone pushover paths,
including descending-load and negative-load branches that fixed load control
cannot follow.

For free generalized coordinates `q_f` and load factor `lambda`, each Newton
correction solves the augmented system

```text
[ K_ff       dR_f/dlambda ] [ delta_q_f ] = -[ R_f                 ]
[ w e_control^T       0   ] [ delta_z   ]   [ w(q_control-q_target) ]
```

where `delta_z` is the scaled load-factor coordinate. The load column is not
assumed to be `-F_ref` when proportional support movements exist. It is assembled
as

```text
dR_f/dlambda = S_f (K_fp ubar_p - F_ref,f)
```

and both the displacement and load-factor columns have parent-bound central
finite-difference tests.

Every trial starts from the same immutable accepted checkpoint. A step commits
the full frame displacement and material state only when equilibrium, controlled
coordinate, correction, parent-binding, and no-fallback gates all pass. Failure
returns the exact parent object and bytes. A persisted accepted checkpoint can be
loaded and supplied as `initial_checkpoint` to resume the remaining targets.

```python
from structural_analysis.assembly.stateful_corotational_fiber_frame2d_displacement_control import (
    StatefulCorotationalFiberFrame2DDisplacementControlConfig,
    run_stateful_corotational_fiber_frame2d_displacement_control_path,
)

result = run_stateful_corotational_fiber_frame2d_displacement_control_path(
    problem,
    (-0.01, -0.02, -0.03),
    control_global_dof=tip_uy_global_dof,
    config=StatefulCorotationalFiberFrame2DDisplacementControlConfig(),
)
```

This is an internal dense CPU candidate. It does not change the unified nonlinear
frame API or J1–J5 public-candidate contract. Rotational control, native sparse
augmented factorization, follower and distributed loads, member releases and
offsets, independent Level 2 comparisons, engineering design authority, and
release promotion remain open.
