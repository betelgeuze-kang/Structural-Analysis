# Phase 2 stateful axial matrix-free Newton bridge

This slice connects the existing accepted/trial material-state assembly to the
load-controlled matrix-free Newton and CPU FGMRES contracts. It closes a narrow
architectural gap: the previous matrix-free continuation checkpoint contained
only displacement state, while material commit and rollback existed only on the
assembled dense/sparse Newton path.

## Step contract

One physical load step is represented as an increment-space problem:

```text
u(eta)      = u_accepted + delta_u
lambda(eta) = lambda_accepted + eta * delta_lambda
R           = F_internal(u, accepted_material_state) - F_external(lambda)
J v         = K_consistent(u, accepted_material_state) v
```

The inner continuation always starts from `delta_u=0, eta=0` and targets
`eta=1`. This permits an arbitrary previously committed physical load and
displacement state without weakening the generic zero-state checkpoint
contract.

Every residual, tangent action, predictor, and line-search candidate in the
step is evaluated from the same immutable accepted material parent. The source
mesh, boundary/load data, element geometry, response kind, and canonical
material parameters are included in a source-problem contract hash. That hash,
the accepted-state hash, target load, equation order, residual formula, and
reference load are bound into the matrix-free operator identity.

Commit occurs only when all of the following pass:

- the current-state FGMRES solve and its independent explicit residual replay;
- strict nonlinear residual-decrease line search;
- nonlinear residual and absolute-or-relative increment gates;
- zero fallback and zero regularization;
- final assembly from the exact accepted material parent;
- a byte check proving the accepted parent did not change during trial work.

On success, displacement and integration-point states are committed together in
a new `StatefulAxialAcceptedState`. On failure, the original state object,
canonical state bytes, and every material-state byte string are retained.

## Focused verification

`tests/test_stateful_axial_matrix_free_newton.py` covers:

- a centered finite-difference JVP check on the same accepted material parent;
- a yielding two-element steel step with matrix-free current-tangent solves,
  line-search history, residual/increment gates, and material-state commit;
- an iteration-limited rejected step with exact displacement and material-state
  rollback;
- deterministic cyclic replay and restart from an accepted material state;
- two-element steel, concrete damage, composite section, and nonlinear link
  paths, all with fallback and regularization counts equal to zero;
- fail-closed rejection of ambiguous pseudo-load targets and empty free-equation
  spaces.

Run the focused suite with:

```bash
PYTHONPATH=src python3 -m pytest -q \
  tests/test_stateful_axial_matrix_free_newton.py \
  tests/test_load_controlled_matrix_free_newton.py \
  tests/test_matrix_free_cpu_fgmres_state_tangent.py \
  tests/test_state_updated_steel_material_newton.py \
  tests/test_state_updated_concrete_damage_newton.py \
  tests/test_state_updated_composite_section_newton.py \
  tests/test_state_updated_bilinear_link_newton.py
```

## Claim boundary

This bridge covers only the existing one-dimensional axial-chain material
families on the local CPU diagnostic FGMRES path. The load targets are explicit;
adaptive step reduction and arc-length are not connected here. The reference
predictor uses a materialized accepted-state tangent, and the current operator
callback and SciPy SuperLU preconditioner remain outside end-to-end
cross-platform deterministic and production claims.

It does not alter the current actual-MGT continuation receipt: that receipt
still has no frame/shell material integration-point state. General
frame/shell material coupling, a durable binary material checkpoint, adaptive
full-load continuation, production sparse preconditioning, ROCm/HIP parity, and
authoritative G1 full-building closure remain false.
