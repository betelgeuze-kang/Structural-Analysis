# Fiber-frame nonlinear kinematic/material state binding

## Purpose

PR-J3 produces one committed nonlinear kinematic state per accepted checkpoint.
PR-I produces one committed `MaterialStateBundle` projection per the same
checkpoint. PR-J4 joins those independent histories and proves that the material
bundle at each epoch was explicitly bound to the exact J3 committed-state hash.

```text
CheckpointChain
   ├─ J3 KinematicStateChain
   │     K0 -> K1 -> K2 ... Kn
   └─ MaterialStateProjectionChain
         B0 -> B1 -> B2 ... Bn

J4 row i requires:
  checkpoint(Ki) == checkpoint(Bi)
  epoch(Ki)      == epoch(Bi)
  Bi.solver_state_hash == Ki.state_hash
```

The join also binds the J1 execution-topology plan and J2 physical-equation
scaling receipt.

## Construction

```python
from structural_analysis.assembly.stateful_fiber_frame2d_nonlinear_state_binding import (
    create_fiber_frame_nonlinear_state_binding,
    create_material_projection_chain_for_kinematic_states,
)

material_chain = create_material_projection_chain_for_kinematic_states(
    problem,
    topology_plan,
    checkpoint_chain,
    kinematic_chain,
)

binding = create_fiber_frame_nonlinear_state_binding(
    problem,
    topology_plan,
    physical_equation_scaling,
    checkpoint_chain,
    kinematic_chain,
    material_chain,
)
```

The helper passes the exact `kinematic_chain.solver_state_hashes` sequence to the
material projection builder and uses the J3 ModelIR and J1 plan hashes.

## Epoch-wise row

Every `FiberFrameNonlinearStateBindingRow` binds:

- checkpoint and parent-checkpoint hashes;
- epoch, step index, and load factor;
- J3 committed kinematic-state hash;
- material projection receipt hash;
- committed MaterialStateBundle hash and parent hash;
- the bundle's solver-state hash;
- integration-point ordering hash;
- member/IP/fiber source-identity hash.

The row is valid only when:

```text
material_bundle_solver_state_hash == kinematic_state_hash
```

Rows are append-stable. Extending a valid checkpoint chain changes the outer J4
binding hash but does not rewrite historical row identities.

## Complete envelope

The outer binding additionally commits:

- complete checkpoint-chain hash;
- J3 kinematic-state-chain hash;
- material projection-chain hash;
- J2 physical-equation-scaling binding and Engine v2 scaling hashes;
- problem and ModelIR identity;
- J1 plan ID/hash and solver-coordinate-scaling hash;
- root and terminal checkpoint hashes;
- root and terminal kinematic-state hashes;
- root and terminal MaterialStateBundle hashes.

A persisted checkpoint-chain roundtrip must recreate the exact same J3 chain,
material chain, J4 rows, and outer binding hash.

## Fail-closed boundaries

J4 rejects:

- different checkpoint histories;
- different ModelIR or J1 plan hashes;
- a J2 scaling receipt bound to another topology;
- material projection count or epoch mismatch;
- material bundle and J3 state hash mismatch;
- checkpoint, step, or load-factor mismatch;
- non-committed material bundles;
- coherent row/envelope rehash after source substitution;
- authority-profile or manifest-field promotion.

## Authority boundary

J4 establishes one combined nonlinear state-transport ancestry, but it does not
prove the constitutive transition or solver terminal conditions. It grants no:

- residual or increment convergence authority;
- nonlinear numerical-result authority;
- displacement result authority;
- reaction, member-force, section, or fiber-output authority;
- design/code authority;
- release readiness or commercial use.

The next product-truth PR must bind J2 residual traces and the accepted terminal
J4 state to a `NonlinearTerminalReceipt`. Only a separate adapter may then issue
a bounded `NonlinearNumericalResultIR`; engineering recovery remains a later
exact replay operator.

## Focused verification

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q \
  tests/test_stateful_fiber_frame2d_nonlinear_state_binding.py \
  tests/test_stateful_fiber_frame2d_kinematic_state_chain.py \
  tests/test_stateful_fiber_frame2d_material_state_projection_chain.py
```
