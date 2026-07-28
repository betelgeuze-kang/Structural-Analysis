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

## Remaining P1 continuation work

Direct displacement control does not by itself provide general limit-point
traversal. Arc-length continuation and an independent external Frame3D
comparison remain required before any broader numerical-authority claim.

## Focused verification

```bash
PYTHONPATH=src python3 -m pytest -q \
  tests/test_stateful_corotational_frame3d_sparse.py \
  tests/test_stateful_corotational_frame3d_displacement_control.py \
  tests/test_stateful_corotational_fiber_frame3d.py \
  tests/test_stateful_corotational_frame3d_materials.py \
  tests/test_stateful_corotational_partial_composite_frame3d.py
```
