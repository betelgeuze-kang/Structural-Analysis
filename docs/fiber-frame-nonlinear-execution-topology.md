# Fiber-frame nonlinear execution topology and coordinate scaling

## Decision

The fiber-frame path does **not** reuse Engine v2 `ExecutionPlan v1` or
`StateIR v1` as its complete nonlinear plan/state description.

Those v1 manifests explicitly bind:

```text
analysis.type = linear_static
operator graph = linear_solve
state schema = structural-analysis-state-ir.v1
constitutive mode = stateless_linear_elastic
```

The stateful RC fiber-frame solver instead owns a nonlinear external
constitutive history carried by committed checkpoints and the merged
`MaterialStateProjectionChain` from PR #132. Treating the linear v1 manifests as
neutral containers would therefore be semantically false.

The selected #133 architecture is an additive typed nonlinear kinematic binding
path:

```text
PR-J1  nonlinear six-DOF topology + solver-coordinate scaling
PR-J2  physical force/moment EquationScaling + residual trace
PR-J3  nonlinear kinematic-state chain
PR-J4  bind the MaterialStateProjectionChain
```

Existing ExecutionPlan v1, StateIR v1, golden hashes, and authority remain
unchanged.

## PR-J1 contract

`FiberFrameNonlinearExecutionTopologyPlan` freezes:

- exact frame problem contract hash;
- supplied ModelIR content hash;
- deterministic node and member order;
- canonical physical node order `UX, UY, UZ, RX, RY, RZ`;
- current solver node order `UX, UY, RZ`;
- solver-to-physical and physical-to-solver equation maps;
- explicit inactive physical equations `UZ, RX, RY`;
- authored fixed equations mapped into the six-DOF space;
- physical and solver free/constrained partitions;
- 12-equation physical member rows;
- six-equation active member rows;
- deterministic CSR topology over active equations, with diagonal-only inactive
  rows;
- node-coordinate and reference-load byte descriptors;
- source numeric-buffer, entity-mapping, operator, topology, and aggregate plan
  hashes.

The plan is a non-authoritative compiler artifact. It is intentionally not
named or serialized as Engine v2 ExecutionPlan v1.

## Solver-coordinate scaling

The current Newton solver expresses every generalized unknown in length units.
For one solver node:

```text
q = [UX_m, UY_m, RZ_generalized_m]
u = [UX_m, UY_m, RZ_rad]
```

With characteristic solver coordinate length `Lq`:

```text
u = S q
S = diag(1, 1, 1/Lq)
q = S^-1 u
```

The generalized residual and Jacobian used by the existing solver are:

```text
r_generalized = S r_physical
K_generalized = S K_physical S
```

`FiberFrameSolverCoordinateScalingReceipt` binds:

- exact `rotation_coordinate_scale_m = Lq`;
- `physical_from_generalized_scale`;
- `generalized_from_physical_scale`;
- reference physical load in solver order;
- reference generalized load;
- source problem, fixed/free equation, and load commitments;
- exact array byte descriptors and canonical scaling hash.

The contract exposes the same residual and Jacobian transforms as executable,
bounded helpers:

```python
generalized_residual = physical_3dof_residual_to_solver_generalized(
    plan, physical_residual
)
generalized_jacobian = physical_3dof_jacobian_to_solver_generalized(
    plan, physical_jacobian
)
```

Focused regression compares both helpers directly with the current frame
assembly's free-equation residual and Jacobian. External scaling-vector bytes
are validated independently against the retained descriptors.

This receipt describes a coordinate transform. It is **not** the physical
EquationScaling contract used to judge mixed force and moment convergence.
That separate PR-J2 contract must retain raw force norms, raw moment norms,
scaled norms, governing node/DOF, and its own characteristic-length provenance.

## Physical mapping

The solver-to-physical component mapping is:

```text
solver UX -> physical UX
solver UY -> physical UY
solver RZ -> physical RZ
```

The inactive components are always:

```text
physical UZ = 0
physical RX = 0
physical RY = 0
```

Helpers provide exact bounded transformations:

```python
physical = solver_generalized_to_physical_3dof(plan, generalized)
canonical = physical_3dof_to_canonical_6dof(plan, physical)
physical_again = canonical_6dof_to_physical_3dof(plan, canonical)
generalized_again = physical_3dof_to_solver_generalized(plan, physical_again)
```

Gathering a canonical six-DOF vector fails closed if an inactive coordinate is
nonzero.

## Sparse topology

Each member retains both representations:

```text
member_physical_global_dofs  12 equations
member_active_physical_dofs   6 equations
member_solver_global_dofs     6 equations
```

The J1 CSR pattern couples the active `UX, UY, RZ` equations for each member.
Inactive `UZ, RX, RY` equations retain a diagonal entry only. The pattern is a
compiler commitment, not an assembled tangent or a backend binding.

## Source identity and tamper boundary

The plan identity changes when any of the following changes:

- problem contract;
- node IDs or member order;
- member connectivity or element contract;
- node coordinates;
- authored fixed equations;
- reference load;
- rotation coordinate scale;
- solver/physical equation map;
- sparse pattern.

Raw arrays remain separate immutable artifacts. Their descriptors bind dtype,
shape, layout, byte length, data hash, and metadata-plus-data content hash.
Imported descriptor-only manifests additionally fail closed on nested binding,
entity-count, DOF-layout, constraint-map, CSR-profile, scaling-map, descriptor
shape, and byte-length incoherence even when the attacker recomputes every
container hash.

## Authority boundary

J1 grants no authority over:

- solver convergence;
- nonlinear state history;
- material state history;
- displacement results;
- reactions or member forces;
- fiber stress/strain output;
- design or code compliance;
- release readiness or commercial use.

PR-J3 must introduce the nonlinear kinematic-state chain. It may reference
StateIR v1 only as an optional canonical displacement carrier and must never
reinterpret its `stateless_linear_elastic` profile as the complete nonlinear
state. PR-J4 then binds that kinematic chain to PR #132's material-state
projection chain.

## Focused validation

```bash
PYTHONPATH=src python3 -m pytest -q \
  tests/test_stateful_fiber_frame2d_execution_topology.py \
  tests/test_verify_quality_gate_contract.py

python3 -m ruff check \
  src/structural_analysis/assembly/stateful_fiber_frame2d_execution_topology.py \
  tests/test_stateful_fiber_frame2d_execution_topology.py

python3 -m ruff format --check \
  src/structural_analysis/assembly/stateful_fiber_frame2d_execution_topology.py \
  tests/test_stateful_fiber_frame2d_execution_topology.py
```
