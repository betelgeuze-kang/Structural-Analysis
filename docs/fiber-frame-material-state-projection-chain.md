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

Exactly one solver-state hash is required for every retained checkpoint. PR-J3's
typed nonlinear kinematic-state chain now supplies that exact hash sequence.
The hashes are not Engine v2 StateIR v1 claims: StateIR v1 remains a
`stateless_linear_elastic` contract and may only be used later as an explicitly
optional canonical displacement carrier.

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

PR-J4 must compose this material projection chain with PR-J3's exact nonlinear
kinematic-state chain. It must require the projection chain's solver-state hash
sequence to equal the J3 committed-state hashes, and it must bind the terminal
MaterialStateBundle without granting terminal or ResultIR authority.

## Focused validation

```bash
PYTHONPATH=src python3 -m pytest -q \
  tests/test_stateful_fiber_frame2d.py \
  tests/test_engine_v2_material_state_bundle_v1.py \
  tests/test_stateful_fiber_frame2d_material_state_bundle.py \
  tests/test_stateful_fiber_frame2d_material_state_projection_chain.py
```
