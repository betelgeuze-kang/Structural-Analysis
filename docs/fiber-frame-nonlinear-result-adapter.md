# Fiber-frame nonlinear numerical-result adapter

This slice converts the bounded J1--J5 stateful fiber-frame solve into an
authoritative `NonlinearNumericalResultIR v1` without pretending that the
fiber-frame state is `StateIR v1`.

The implementation is
`src/structural_analysis/assembly/stateful_fiber_frame2d_nonlinear_result_adapter.py`.
It retains and replays the complete source chain whenever an in-memory result
is validated.

## Source chain

```text
bounded fiber-frame problem
  -> J1 execution topology
  -> J2 physical equation scaling
  -> checkpoint chain
  -> J3 canonical six-DOF kinematic state chain
  -> material-state projection chain
  -> J4 combined execution-state binding
  -> actual Newton load path
  -> J5 terminal convergence receipt
  -> source binding + four result receipts
  -> NonlinearNumericalResultIR v1
```

The source binding records exact hashes for the topology, operator and numeric
buffers, both scaling layers, combined execution state, checkpoint and state
chains, terminal J5 receipt, terminal kinematic and material states, and a
path-history hash composed from the checkpoint chain, source load-path replay,
and J5 step-receipt chain.

`StateIR v1` remains intentionally absent. Its current profile is the
stateless-linear-elastic carrier and cannot represent this committed nonlinear
fiber state. The core result contract therefore accepts a replaying,
source-neutral adapter snapshot while preserving the existing legacy
ExecutionPlan/StateIR path and legacy manifest hashes.

## Result receipts

The adapter issues four hash-bound receipts:

1. Reduced-system identity
   - canonical free physical and solver equation orders;
   - reduced CSR row/column topology;
   - terminal same-parent analytic Jacobian identity;
   - no claim that numeric CSR values were materialized or executed.
2. Full residual
   - terminal source three-DOF residual bytes;
   - canonical six-DOF SI residual bytes;
   - dimensionless scaled residual bytes;
   - fixed residual tolerance and passed J5 residual gate.
3. Boundary condition
   - inactive, authored-fixed, constrained, and free physical partitions;
   - constrained/free solver partitions and solver-to-physical map;
   - exact bounded problem, case, node order, and topology.
4. Backend
   - executed deterministic CPU matrix backend and normalized backend role;
   - solver configuration, operator, numeric-buffer, terminal-step, and
     terminal-Jacobian hashes;
   - total linear solves and exact zero fallback/regularization counts.

The terminal section additionally exposes the accepted-step count, full load
factor, residual and increment tolerances, final increment norm, and the passed
residual, increment, and combined convergence gates. The numerical result binds
the immutable terminal canonical six-DOF displacement bytes.

## Authority boundary

This adapter establishes bounded authority for:

- the J5 convergence decision;
- the committed terminal displacement;
- the committed terminal material-state bundle;
- the exact source, residual, boundary, and backend identities listed above.

It does not establish authority for:

- reactions, member forces, section forces, or integration-point engineering
  outputs;
- arbitrary frame topology, boundary conditions, load types, geometric
  nonlinearity, sparse/HIP parity, or performance;
- constitutive-law verification beyond the already bounded source profile;
- design/code approval, release readiness, or commercial use.

The generic nonlinear recovery function rejects this adapter-bound result with
`nonlinear_recovery_source_profile_unsupported`. The next roadmap slice must
provide a fiber-frame-specific exact engineering recovery operator before any
reaction or member-force authority can be promoted.

## Validation levels

`validate_fiber_frame_nonlinear_result_adapter_manifest` validates strict finite
JSON, exact nested keys, canonical section hashes, descriptor metadata, receipt
cross-bindings, terminal gates, and both authority boundaries. It never treats
a descriptor-only manifest as source replay.

`validate_fiber_frame_nonlinear_result_source_binding` replays every retained
J1--J5 input and requires the rebuilt source-binding manifest to be identical.
`validate_fiber_frame_nonlinear_numerical_result_adapter` then replays the core
result source, verifies every normalized `NonlinearNumericalResultIR` binding,
and checks the adapter hash.

## Focused verification

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q \
  tests/test_stateful_fiber_frame2d_nonlinear_result_adapter.py \
  tests/test_stateful_fiber_frame2d_nonlinear_terminal_receipt.py \
  tests/test_engine_v2_nonlinear_result_recovery_v1.py \
  tests/test_engine_v2_nonlinear_recovery_source_binding.py \
  tests/test_engine_v2_core_dependency_boundary.py

python3 -m ruff check \
  src/structural_analysis/assembly/stateful_fiber_frame2d_nonlinear_result_adapter.py \
  src/structural_analysis/engine_v2/contracts/nonlinear_result.py \
  src/structural_analysis/engine_v2/contracts/nonlinear_recovery.py \
  tests/test_stateful_fiber_frame2d_nonlinear_result_adapter.py
```
