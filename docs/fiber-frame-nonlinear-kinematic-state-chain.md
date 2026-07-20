# Fiber-frame nonlinear kinematic-state chain

## Purpose

The bounded `StatefulFiberFrame2DCheckpointChain` stores physical frame
displacements in node-major `[UX m, UY m, RZ rad]` order together with nested
nonlinear element and material state. PR-J1 introduced a separate nonlinear
six-DOF execution-topology plan, but that plan intentionally contains no runtime
state.

PR-J3 adds a typed displacement-state envelope between those two contracts:

```text
checkpoint ancestry
  C0 -------------> C1 -------------> C2 ... Cn
  |                  |                  |       |
  v                  v                  v       v
  K0 --accepted--> T1 --commit--> K1 ...       Kn
```

- `C` is a committed source checkpoint.
- `K` is the one retained committed kinematic state for that checkpoint.
- `T` is a deterministic transient trial state. Its hash is retained in the
  transition receipt, while validation recreates its full manifest and arrays.

The contract transports checkpoint kinematics. It does not replay equilibrium,
constitutive integration, or solver convergence.

## Construction

```python
from structural_analysis.assembly.stateful_fiber_frame2d_kinematic_state_chain import (
    create_fiber_frame_nonlinear_kinematic_state_chain,
)

kinematic_chain = create_fiber_frame_nonlinear_kinematic_state_chain(
    problem,
    execution_topology_plan,
    checkpoint_chain,
)
```

The module remains a direct import and is not re-exported through
`structural_analysis.assembly`.

## Exact state count and lifecycle

The retained `committed_states` tuple has exactly the same length and order as
the checkpoint chain:

```text
len(committed_states) == len(checkpoint_chain.checkpoints)
len(transitions) == len(committed_states) - 1
```

Epoch zero is the unique unparented committed state. Its load factor and all
three displacement arrays are exact zero.

For every positive epoch, validation recreates:

1. a trial state parented by the preceding committed kinematic state;
2. a committed state parented by that trial state;
3. a transition receipt binding the accepted, trial, and committed hashes;
4. the parent and child checkpoint hashes for the same transition.

This is a state-transport lifecycle. It does not claim that the checkpoint is a
converged or physically correct nonlinear solution.

## Displacement arrays

Every retained state owns three immutable little-endian FP64 arrays:

| Array | Node-major order | Units |
|---|---|---|
| `checkpoint_displacement_physical_3dof` | `UX, UY, RZ` | `m, m, rad` |
| `solver_generalized_coordinates_m` | `UX, UY, scaled RZ` | `m, m, m` |
| `canonical_displacement_si` | `UX, UY, UZ, RX, RY, RZ` | `m, m, m, rad, rad, rad` |

The generalized rotation coordinate is derived with the exact J1
`rotation_coordinate_scale_m`. The canonical scatter uses the exact J1
`solver_to_physical_global_dofs` order. `UZ`, `RX`, and `RY` are required to be
bit-exact zero in every retained state.

The canonical vector gathers back to the source checkpoint displacement with
exact array equality. The generalized-coordinate roundtrip uses a bounded FP64
roundoff check because multiplication and division by an arbitrary rotation
scale need not be bitwise inverse operations.

## Bound identities

The outer chain envelope binds the exact complete checkpoint-chain hash and
schema. Every retained state binds only its causal source and ancestry:

- frame problem contract hash and case ID;
- ModelIR content hash;
- J1 nonlinear execution-topology plan ID and hash;
- J1 solver-coordinate-scaling hash;
- exact checkpoint hash and parent checkpoint hash;
- node identity and canonical component order;
- source, generalized, and canonical displacement byte hashes;
- root and terminal checkpoint hashes;
- root and terminal kinematic-state hashes;
- every accepted → trial → committed transition hash.

Changing node identity, plan identity, checkpoint bytes, displacement bytes,
rotation scaling, or any state parent changes the kinematic chain identity.
Appending a valid child checkpoint changes the outer chain hash but preserves
all earlier state and transition hashes; no historical solver-state identity
depends on future descendants.

## Descriptor-only manifest and external bytes

`to_manifest()` emits array descriptors rather than inline vectors. A descriptor
binds dtype, shape, layout, byte length, coordinate-order hash, raw data hash,
and metadata-plus-bytes content hash.

Use
`validate_fiber_frame_nonlinear_kinematic_state_array_bytes(...)` to validate an
external immutable byte payload. Mutable byte containers, wrong lengths,
non-finite values, and hash mismatches fail closed.

The state and chain manifest validators separately enforce exact keys, scalar
types, profile values, lifecycle links, claim-boundary booleans, descriptor
shapes, and canonical hashes.

Claim boundaries are scoped per artifact. A state claims only its checkpoint and
displacement mapping, a transition claims only adjacent lifecycle hashes, and
only the outer envelope claims the complete checkpoint chain and full replay.

## Persisted checkpoint replay

The checkpoint chain remains the restart artifact. J3 does not add a second
kinematic persistence format. Dumping and reloading the canonical checkpoint
chain, then recompiling against the same J1 plan, must produce identical:

- committed state manifests;
- displacement array bytes;
- transition receipts;
- solver-state hash sequence;
- terminal state hash;
- chain hash.

## StateIR v1 boundary

J3 deliberately does not create an Engine v2 `StateIR v1` object.

`StateIR v1` declares `stateless_linear_elastic` constitutive semantics and is
therefore not the complete state of this nonlinear fiber-frame path. A later
adapter may use `canonical_displacement_si` only as an explicitly optional
displacement carrier. It must not infer constitutive history or new authority
from StateIR v1.

The J3 manifest records this as:

```text
state_ir_v1_not_emitted_optional_displacement_carrier_only.v1
```

## Authority boundary

J3 proves deterministic kinematic transport and ancestry only. It grants no:

- solver convergence authority;
- nonlinear numerical-result authority;
- reaction, member-force, section, or fiber-output authority;
- constitutive-transition replay authority;
- design or code-compliance authority;
- release readiness or commercial use.

PR-J4 now binds this exact kinematic-state chain and its `solver_state_hashes`
sequence to PR #132's `FiberFrameMaterialStateProjectionChain` through the
[`FiberFrameNonlinearExecutionStateBinding`](fiber-frame-nonlinear-execution-state-binding.md).
Nonlinear terminal, ResultIR, and exact recovery authority remain separate later
contracts.

## Focused verification

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q \
  tests/test_stateful_fiber_frame2d_kinematic_state_chain.py \
  tests/test_stateful_fiber_frame2d_execution_topology.py \
  tests/test_stateful_fiber_frame2d.py

python3 -m ruff check \
  src/structural_analysis/assembly/stateful_fiber_frame2d_kinematic_state_chain.py \
  tests/test_stateful_fiber_frame2d_kinematic_state_chain.py

python3 -m ruff format --check \
  src/structural_analysis/assembly/stateful_fiber_frame2d_kinematic_state_chain.py \
  tests/test_stateful_fiber_frame2d_kinematic_state_chain.py
```
