# Complete fiber-frame material-state projection chain

## Purpose

The persisted `StatefulFiberFrame2DCheckpointChain` proves a complete,
epoch-zero-rooted checkpoint ancestry. The material-state projection chain
composes the pairwise checkpoint adapter over that exact ancestry.

```text
checkpoint chain
  C0 -> C1 -> C2 -> ... -> Cn
   |     |     |             |
   v     v     v             v
  B0 -> T1 -> B1 -> T2 -> B2 ... -> Bn
```

`C` values are committed frame checkpoints, `T` values are trial
MaterialStateBundles, and `B` values are committed MaterialStateBundles.

## Construction

```python
projected = create_fiber_frame_material_state_projection_chain(
    problem,
    checkpoint_chain,
    model_ir_content_hash=model_hash,
    execution_plan_hash=plan_hash,
    solver_state_hashes=(state0_hash, state1_hash, state2_hash),
)
```

Exactly one solver `StateIR` hash is required for every retained checkpoint.
The solver-state sequence is not inferred from checkpoint bytes because the
bounded frame checkpoint currently uses a three-DOF-per-node solver state while
Engine v2 StateIR compilation is a separate follow-up contract.

## Bound identities

The projection-chain envelope binds:

- exact checkpoint-chain hash;
- exact frame problem contract hash;
- one ModelIR content hash;
- one ExecutionPlan hash;
- root and terminal checkpoint state hashes;
- one solver-state hash per checkpoint;
- every checkpoint-to-trial-to-committed material bundle transition;
- terminal MaterialStateBundle hash;
- every constituent material byte hash through the nested projections.

Changing only the solver-state history changes the projection-chain hash even
when the checkpoint chain is identical.

## Validation

Validation replays every transition against the complete checkpoint ancestry:

1. validate the checkpoint chain and its exact genesis;
2. validate the epoch-zero material projection;
3. validate each child checkpoint against its preceding checkpoint;
4. recreate each trial bundle from the accepted material bundle;
5. recreate each committed bundle from that trial;
6. require one model and execution-plan binding across the chain;
7. require material-bundle epoch to equal checkpoint-chain position;
8. recompute the projection-chain canonical hash.

A persisted checkpoint-chain roundtrip must produce the identical material
projection chain.

## Authority boundary

The projection chain proves state-transport ancestry only. It does not prove that
one checkpoint is the physically correct constitutive update from the preceding
checkpoint. The source checkpoint solver already verifies parent binding and
commit/rollback, but constitutive-transition replay remains a separate future
operator.

The chain therefore grants no:

- solver convergence authority;
- nonlinear numerical result authority;
- reaction/member-force/fiber-output authority;
- design or code authority;
- release or commercial authority.

## Follow-up

The next adapter should compile each checkpoint into an exact Engine v2
`StateIR` under one versioned `ExecutionPlan`. Its equation-scaling contract must
bind the frame's `rotation_coordinate_scale_m` so force and moment equations are
not judged by an unscaled mixed-unit residual norm.

## Focused validation

```bash
PYTHONPATH=src python3 -m pytest -q \
  tests/test_stateful_fiber_frame2d.py \
  tests/test_engine_v2_material_state_bundle_v1.py \
  tests/test_stateful_fiber_frame2d_material_state_bundle.py \
  tests/test_stateful_fiber_frame2d_material_state_projection_chain.py
```
