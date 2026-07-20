# Fiber-frame nonlinear kinematic-state chain

## Purpose

PR-J3 projects the complete committed fiber-frame checkpoint ancestry into a
typed kinematic-state chain without changing Engine v2 StateIR v1.

```text
checkpoint displacement [UX, UY, RZ]
    ├─ physical solver-order displacement
    ├─ J1 generalized solver coordinates
    └─ canonical six-DOF displacement [UX, UY, UZ, RX, RY, RZ]
```

The contract binds J1 topology, J2 physical equation scaling, checkpoint
ancestry, and exact displacement bytes. Constitutive history remains in the
separate MaterialStateProjectionChain merged through PR #132.

## Why this is separate from StateIR v1

StateIR v1 explicitly identifies the `stateless_linear_elastic` profile. The
stateful RC fiber-frame path has external nonlinear constitutive history and
must not reinterpret that v1 manifest as a complete nonlinear state.

The J3 state is therefore an additive, non-authoritative transport contract.
A later adapter may reference a StateIR v1 displacement carrier only if its
limited meaning remains explicit.

## State views

Each checkpoint produces three immutable arrays:

```text
physical_displacement_solver_order
  node-major [UX_m, UY_m, RZ_rad]

generalized_coordinates_solver_order
  node-major [UX_m, UY_m, RZ_generalized_m]

canonical_displacement_6dof
  node-major [UX_m, UY_m, UZ_m, RX_rad, RY_rad, RZ_rad]
```

Inactive `UZ`, `RX`, and `RY` entries must remain exact zero.

## Chain binding

The chain requires:

- exact epoch-zero-rooted checkpoint-chain hash;
- one J1 topology-plan hash;
- one J2 physical-scaling hash;
- one problem contract;
- contiguous checkpoint epochs and parents;
- one kinematic-state hash per checkpoint;
- root and terminal checkpoint/state identities;
- deterministic descriptor-only manifests.

A persisted checkpoint-chain roundtrip must produce the identical kinematic
chain and identical displacement bytes.

## Authority boundary

The J3 state and chain do not establish:

- Newton convergence;
- constitutive-state history;
- nonlinear numerical-result authority;
- reaction, member-force, or fiber-output authority;
- design/code authority;
- release or commercial authority.

PR-J4 joins each J3 state with the corresponding PR #132 material-state
projection by checkpoint, epoch, and solver-state hash. Only after that join may
a later terminal gate promote a committed nonlinear numerical state.
