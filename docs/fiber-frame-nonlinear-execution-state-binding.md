# Fiber-frame nonlinear execution/state binding

## Purpose

PR-J4 closes issue #133's non-authoritative design gate. It composes the exact
artifacts introduced by J1-J3 and the material projection chain from PR #132:

```text
J1 nonlinear execution topology + solver-coordinate scaling
                         |
J2 physical EquationScaling v1 binding
                         |
checkpoint chain -> J3 kinematic states K0 -> K1 -> ... -> Kn
       |                         == solver_state_hash
       +------------> material bundles B0 -> B1 -> ... -> Bn
                         |
                         v
          J4 nonlinear execution/state binding
```

The result is one deterministic identity envelope for scaled execution
topology, committed checkpoint kinematics, and committed material-state
history. It is not an Engine v2 `ExecutionPlan v1`, `StateIR v1`, terminal
state, or `ResultIR`.

## Construction

```python
from structural_analysis.assembly.stateful_fiber_frame2d_nonlinear_execution_state_binding import (
    create_fiber_frame_nonlinear_execution_state_binding,
)

binding = create_fiber_frame_nonlinear_execution_state_binding(
    problem,
    execution_topology_plan,
    physical_equation_scaling,
    checkpoint_chain,
    kinematic_state_chain,
    material_state_projection_chain,
)
```

The module remains a direct import and is not re-exported through
`structural_analysis.assembly`.

## Scaled execution identity

The outer binding records and replays:

- the exact J1 plan ID and plan hash;
- topology, operator, and numeric-buffer hashes;
- the J1 solver-coordinate-scaling hash;
- the J2 physical EquationScaling binding hash;
- the unchanged Engine v2 `EquationScaling v1` hash;
- the Engine scaling source-commitment hash;
- canonical physical equation-order hash;
- exact free-equation content hash;
- exact physical scale-vector content hash;
- problem, ModelIR, case, and node order.

The free-equation identity plus the scale-vector content hash fixes the exact
free-DOF divisors consumed by a later solver. J4 does not retain a residual
trace and does not judge convergence. Raw translational norms remain in N, raw
rotational norms remain in N·m, and only the separately defined scaled norm is
dimensionless.

## Exact per-checkpoint composition

There is exactly one `FiberFrameNonlinearExecutionStateEpochBinding` for each
checkpoint. Every row binds:

- checkpoint and parent checkpoint hashes;
- accepted, transient-trial, and committed kinematic-state hashes;
- material projection receipt hash;
- accepted, transient-trial, and committed MaterialStateBundle hashes;
- physical EquationScaling binding hash;
- epoch, step index, and load factor;
- shared problem, model, plan, case, and authority profiles.

The essential J4 equality is enforced for every epoch:

```text
J3 committed kinematic state hash
  == material projection receipt solver_state_hash
  == committed MaterialStateBundle solver_state_hash
```

An independently valid material projection chain with arbitrary solver-state
hashes therefore cannot be composed. Model hash, plan hash, checkpoint ancestry,
epoch coordinates, and load factor must also agree exactly.

Epoch zero has no parent, accepted, or trial hashes and has exact zero load
factor. Every positive epoch links the preceding committed kinematic and
material states to separate transient trial hashes and then to the retained
committed states.

## Bound chain terminals

The outer binding fixes:

- complete checkpoint-chain hash;
- complete J3 kinematic-state-chain hash;
- complete material-state-projection-chain hash;
- root and terminal checkpoint hashes;
- root and terminal kinematic-state hashes;
- root and terminal MaterialStateBundle hashes;
- the ordered solver-state and material-bundle hash sequences.

The epoch rows do not include either complete future chain hash. Appending a
valid descendant changes the outer binding hash but preserves all historical
epoch-binding hashes.

## StateIR v1 decision

J4 preserves the option-2 architecture selected in issue #133. `StateIR v1`
is not emitted and its `stateless_linear_elastic` profile is never treated as
the nonlinear constitutive state.

The binding carries the exact J3 usage profile:

```text
state_ir_v1_not_emitted_optional_displacement_carrier_only.v1
```

A later adapter may use the canonical J3 displacement only as an explicitly
optional carrier. It cannot infer material history, convergence, terminal
status, results, or recovery authority from StateIR v1.

## Validation and persistence

Full validation replays each source contract before rebuilding the J4 binding:

1. J1 plan validation against the exact frame problem;
2. J2 geometry/load/unit/equation-scale replay against that plan;
3. exact persisted checkpoint ancestry and genesis validation;
4. J3 kinematic state and trial/commit replay;
5. material projection and MaterialStateBundle lifecycle replay;
6. cross-chain checkpoint and solver-state equality at every epoch;
7. exact reconstruction of all epoch rows and the outer canonical hash.

Descriptor-only manifest validation checks exact keys, scalar/container types,
schema versions, fixed authority booleans, cross-epoch ancestry, and canonical
hashes. It does not substitute for replay against the external source objects.

Dumping and loading the checkpoint chain, then rebuilding the J3 and material
chains, produces an identical J4 manifest and binding hash.

## Authority boundary

J4 proves deterministic scaled topology and state-transport composition only.
The material projection replays bundle lifecycle and exact bytes from retained
checkpoints; it does not replay the constitutive update law itself.

J4 grants no:

- solver convergence authority;
- nonlinear numerical-result authority;
- terminal-state or `ResultIR` authority;
- reaction, member-force, section, or fiber-recovery authority;
- design or code-compliance authority;
- release readiness or commercial use.

Any nonlinear terminal contract must separately consume this exact binding,
the actual consistent residual/Jacobian path, physical EquationScaling, and
explicit convergence evidence. ResultIR and exact engineering recovery remain
later, separate contracts.

PR-J5 now supplies that separate bounded terminal contract in
[fiber-frame-nonlinear-terminal-receipt.md](fiber-frame-nonlinear-terminal-receipt.md).
It replays the exact J4 sources and actual full-load Newton path, rebuilds J2
physical residual traces, and finite-difference audits every same-parent
Jacobian. J4 itself remains non-authoritative, while J5 grants convergence only
for the bounded path and still grants no numerical-result or recovery
authority.

## Focused verification

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q \
  tests/test_stateful_fiber_frame2d_nonlinear_execution_state_binding.py \
  tests/test_stateful_fiber_frame2d_kinematic_state_chain.py \
  tests/test_stateful_fiber_frame2d_material_state_projection_chain.py \
  tests/test_stateful_fiber_frame2d_physical_equation_scaling.py

python3 -m ruff check \
  src/structural_analysis/assembly/stateful_fiber_frame2d_nonlinear_execution_state_binding.py \
  tests/test_stateful_fiber_frame2d_nonlinear_execution_state_binding.py

python3 -m ruff format --check \
  src/structural_analysis/assembly/stateful_fiber_frame2d_nonlinear_execution_state_binding.py \
  tests/test_stateful_fiber_frame2d_nonlinear_execution_state_binding.py
```
