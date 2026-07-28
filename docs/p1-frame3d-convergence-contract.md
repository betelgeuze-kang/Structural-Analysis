# Frame3D convergence and continuation contract

The stateful corotational Frame3D sparse path is an experimental bounded
candidate. It has no release or independent external-V&V authority. This
document records the solver conditions that are implemented and the
continuation capabilities that remain open.

## Step commit contract

An accepted load step requires all of the following:

- dimensionless 6DOF scaled residual and increment gates
- a valid positive backtracking line-search step whenever correction is needed
- admissible material trials from one immutable accepted parent
- final reassembled equilibrium and material-state consistency
- passing sparse factorization diagnostics
- no regularization and no fallback

Raw translation/rotation residuals and increments, the characteristic length,
scaled values, scaled condition estimate, and scaling hash remain attached to
the iteration trace.

## Adaptive load cutback

`StatefulCorotationalFrame3DSparseConfig` binds the cutback reduction factor,
minimum load-factor increment, and maximum cutback attempts per requested
target into the solver contract hash. A retriable failure starts the next
attempt from the last accepted checkpoint, never from the rejected trial.

The controller currently retries bounded nonconvergence, line-search failure,
invalid geometry/material trials, invalid Newton corrections, and sparse
factorization failure. An unsupported constitutive path is not made admissible
by shrinking the step and therefore fails closed without cutback.

Before every attempt, the accepted checkpoint is serialized to canonical bytes.
A failed attempt is eligible for cutback only when those bytes remain exactly
unchanged. Every accepted intermediate substep receives its own checkpoint and
parent hash before the original requested target is attempted again.

The `stateful-corotational-frame3d-sparse-result.v2` receipt separates:

- requested load factors
- every attempted load factor and its accepted/rolled-back outcome
- the parent checkpoint and cutback count for each attempt
- stable failure codes and the next reduced target
- per-failure exact rollback evidence
- whether adaptive cutback was actually used

When no attempt failed, `failed_attempt_rollback_exact` is `null`; the result
does not manufacture a successful rollback observation for a path that never
rolled back.

If the retry limit or minimum increment is reached, the solver raises
`adaptive_load_cutback_exhausted` and attaches the complete attempt receipt to
the exception. No unconverged checkpoint is published.

## Direct displacement control

`solve_stateful_corotational_frame3d_displacement_control_path` solves one free
translational UX/UY/UZ coordinate and the proportional nodal-load factor
together. Rotational and multiple-coordinate control remain unsupported.

The augmented system is dimensionless:

```text
residual = [D_R^-1 R; (u_control - u_target) / u_control_ref]
jacobian = [D_R^-1 K D_u, D_R^-1 (-P);
            e_control^T D_u / u_control_ref, 0]
```

`u_control_ref` is explicit evidence derived from the parent coordinate, target,
target increment, and configured absolute control tolerance. This prevents a
small target from being silently underweighted against the equilibrium
equations. A step commits only after scaled equilibrium, scaled control,
scaled displacement increment, load-factor increment, augmented sparse
diagnostic, line-search, material admissibility, final reassembly, parent
immutability, no-regularization, and no-fallback gates all pass.

Accepted states use the same generic physical Frame3D checkpoint chain, while
the direct-control result separately binds the controlled DOF, ordered targets,
direct-control contract hash, convergence trace, and augmented diagnostics.
Prefix plus resume reproduces the uninterrupted terminal checkpoint exactly.
Failure exposes a stable code and exact parent-rollback receipt; no failed trial
is checkpointed.

## Scaled spherical arc-length continuation

`stateful_corotational_frame3d_arc_length_continuation` traces one proportional
nodal-load path with a free translational UX/UY/UZ monitor. The displacement
coordinates and equilibrium equations use the common 6DOF scaling:

```text
q_translation = u / L_char
q_rotation    = theta
R_scaled      = D_R^-1 R
K_scaled      = D_R^-1 K D_u
```

The load factor is included in a dimensionless spherical constraint:

```text
delta_q^T delta_q
  + (load_factor_metric_scale * delta_lambda)^2
  = arc_length^2
```

Every predictor uses a passing sparse solve and orients its tangent against the
last accepted unit tangent. Every corrector solves the dimensionless augmented
equilibrium/constraint Jacobian and applies backtracking to a normalized
scaled-residual/constraint merit. Commit additionally requires scaled residual,
constraint, scaled coordinate increment, load-factor increment, line-search,
material admissibility, final reassembly, parent immutability, sparse
diagnostics, no-regularization, and no-fallback gates.

Failed retriable attempts serialize and compare the exact parent checkpoint,
then reduce only the arc radius. The boundary checkpoint binds the generic
physical state checkpoint, current radius, previous unit tangent, attempt
counters, path contract, and its own hash. Resume from either a committed or
rolled-back boundary reproduces the uninterrupted terminal state exactly.
Unsupported constitutive paths are non-retriable.

The result receipt exposes raw translation/rotation residual and increment
observations, dimensionless scaled observations, characteristic length,
reference force, scaling hash, augmented condition estimate and scope,
constraint residual, adaptive-radius use, and separate failed-attempt rollback
evidence. When there is no accepted step or no failed attempt, the corresponding
observation is `null`; the receipt does not manufacture a numeric zero or a
successful rollback.

The focused shallow-arch test crosses the first maximum load, follows a
descending branch into negative load factor, and reaches the configured
displacement target without regularization or fallback. This is bounded
in-repository evidence, not independent external validation.

## Remaining P1 authority work

An independent external Frame3D comparison remains required before any broader
numerical-authority or release claim. The arc-length profile does not support
rotational or multiple monitor constraints, non-proportional or follower loads,
or a general prescribed-displacement pattern.

## Focused verification

```bash
PYTHONPATH=src python3 -m pytest -q \
  tests/test_stateful_corotational_frame3d_sparse.py \
  tests/test_stateful_corotational_frame3d_displacement_control.py \
  tests/test_stateful_corotational_frame3d_arc_length.py \
  tests/test_stateful_corotational_fiber_frame3d.py \
  tests/test_stateful_corotational_frame3d_materials.py \
  tests/test_stateful_corotational_partial_composite_frame3d.py
```
