# Fiber-frame checkpoint to MaterialStateBundle projection

## Purpose

The bounded stateful RC fiber-frame path already owns an exact restart artifact:
`StatefulFiberFrame2DCheckpoint`. The checkpoint binds the frame problem,
committed global displacement, epoch, parent checkpoint, member states, beam
integration-point section states, and constituent steel/concrete states.

This adapter projects those constituent states into Engine v2
`MaterialStateBundle` without replacing the checkpoint codec.

```text
StatefulFiberFrame2DCheckpoint
  member order
    -> beam integration-point order
      -> section fiber order
        -> canonical constituent state bytes
            |
            v
MaterialStateBundle
```

The checkpoint remains the restart artifact. `MaterialStateBundle` is the
backend-neutral constitutive-state transport used by later StateIR and ResultIR
contracts.

## Exact supported scope

Adapter v1 accepts only the current bounded family:

- `StatefulFiberFrame2DProblem`;
- committed `StatefulFiberFrame2DCheckpoint`;
- `StatefulFiberBeam2D` members;
- exact `StatefulRCFiberSection` sections;
- exact `StatefulFiberSectionState` integration-point states;
- `UniaxialPlasticityState` steel fibers;
- `ConcreteDamageState` concrete fibers.

A different section protocol or material-state codec fails closed. Generalized
section/material codec registration is a separate contract.

## Deterministic source order

Entries are flattened in the exact problem/checkpoint order:

```text
member tuple index
  -> element quadrature index
    -> section fiber tuple index
```

Each entry carries deterministic synthetic bundle identities:

```text
entity_id             member.0000
integration_point_id  ip.0001.fiber.0012
```

The receipt separately binds the source identities and properties:

- member ID and element contract hash;
- integration-point index and quadrature coordinate;
- section ID and section contract hash;
- fiber index, ID, coordinate, area, and material kind;
- material ID and state schema version.

Consequently, changing member, integration-point, or fiber identity/order
changes the source-identity hash. The material bundle ID also embeds prefixes of
the problem-contract and checkpoint-state hashes.

## Constituent bytes

Each entry stores the exact canonical bytes of one material state. For the
current family, the MaterialStateBundle entry data hash equals the material
state's own `state_hash`:

```text
sha256(material_state.canonical_bytes())
```

The projection manifest remains descriptor-only and does not embed those raw
bytes.

## Lifecycle

### Initial checkpoint

```python
projection0 = create_initial_fiber_frame_material_state_projection(
    problem,
    checkpoint0,
    model_ir_content_hash=model_hash,
    execution_plan_hash=plan_hash,
    solver_state_hash=state0_hash,
)
```

The result is an unparented committed epoch-zero MaterialStateBundle.

### Committed child checkpoint

```python
projection1 = advance_fiber_frame_material_state_projection(
    problem,
    checkpoint0,
    checkpoint1,
    projection0,
    solver_state_hash=state1_hash,
)
```

The adapter requires:

- exact parent and child checkpoint validation;
- child epoch and step equal parent plus one;
- child `parent_state_hash` equal parent `state_hash`;
- accepted projection bound to the supplied parent checkpoint;
- unchanged model and execution-plan bindings;
- identical member/IP/fiber identities and order;
- each child constituent state parented by the corresponding accepted entry data
  hash.

Internally it creates one trial bundle and atomically commits it. The projection
receipt records the trial bundle hash, and the committed bundle is parented by
that trial.

## Persistence parity

A checkpoint restored through the strict persisted checkpoint codec must produce
the exact same projection receipt and MaterialStateBundle as the original
in-memory checkpoint. This keeps checkpoint serialization and Engine v2 state
transport from becoming dual truths.

## Authority boundary

The adapter and MaterialStateBundle are non-authoritative state transport. They
do not prove:

- solver residual or increment convergence;
- constitutive-law replay;
- reaction or member-force recovery;
- fiber stress/strain engineering output;
- design or code compliance;
- release readiness or commercial use.

A later adapter must bind the same checkpoint to an exact ExecutionPlan and
committed StateIR. Only a separate nonlinear terminal/result contract may grant
bounded numerical state authority, and engineering recovery needs its own exact
replay operator.

## Focused validation

```bash
PYTHONPATH=src python3 -m pytest -q \
  tests/test_engine_v2_material_state_bundle_v1.py \
  tests/test_engine_v2_material_state_bundle_manifest_lineage.py \
  tests/test_stateful_fiber_frame2d.py \
  tests/test_stateful_fiber_frame2d_material_state_bundle.py

python3 -m ruff check \
  src/structural_analysis/assembly/stateful_fiber_frame2d_material_state_bundle.py \
  src/structural_analysis/assembly/__init__.py \
  tests/test_stateful_fiber_frame2d_material_state_bundle.py
```
