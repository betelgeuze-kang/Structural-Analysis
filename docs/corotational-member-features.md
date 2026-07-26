# Corotational 2D member features

PR 13 closes the bounded product path for planar RZ end releases, rigid end offsets,
and uniform distributed member loads. These features are part of the same immutable
problem hash, nonlinear residual, consistent tangent, checkpoint chain, dense/sparse
parity contract, and engineering recovery as the base corotational fiber member.

## Public contract

An element may add:

```json
{
  "rigid_offsets_global_m": {"i": [0.2, 0.0], "j": [-0.2, 0.0]},
  "end_releases": {"i": [], "j": ["RZ"]},
  "uniform_distributed_load_local": {
    "basis": "initial_member_local",
    "behavior": "dead",
    "qx_kN_per_m": 0.0,
    "qy_kN_per_m": -2.0
  }
}
```

All three objects are exact, fail-closed contracts. Offsets are vectors from the
analysis node to the physical element end in the undeformed global XY system. The only
v1 release component is planar `RZ`. Distributed load values are full-load values and
are scaled by the load factor.

## Operators

For each offset vector `r`, the physical element end is
`x_end = x_node + u_node + (R(theta)-I) r`. Forces return through the transpose of
the exact Jacobian. The residual tangent includes both `B^T K B` and the force-weighted
second derivative of the rigid-arm map, including the conservative dead-load term.

A released end rotation is retained in the element checkpoint state but removed from
the global equation set. Each trial solves
`C^T(f_internal - lambda p_dead) = 0` from the accepted parent state. The converged
internal coordinate is eliminated with the exact Schur complement. Singular release
tangents or a non-decreasing local solve block the trial; no stiffness regularization,
fallback, or silent fixity is applied.

The uniform load vector in initial element-local axes is
`[qxL/2, qyL/2, qyL^2/12, qxL/2, qyL/2, -qyL^2/12]`. Engineering member-end forces
are the net actions `f_internal - lambda p_dead`; section and fiber results remain the
exact deformation-based finite-element states. Reactions include both nodal and member
loads.

## Verification boundary

Focused tests bind:

- same-parent finite-difference parity of the combined offset/load/release tangent;
- released-end equilibrium and deterministic feature-response hashes;
- dense/native-CSR assembly parity;
- full nonlinear load-path convergence and checkpoint validation;
- terminal-parent engineering replay, reaction equilibrium, and zero released-end net
  moment;
- public API execution and exact semantic checkpoint replay.

The bounded contract does not include axial or shear releases, semi-rigid springs,
partial-span or varying loads, follower loads, thermal loads, shear deformation, or 3D
offset/release behavior. External Level 2 verification remains a separate promotion
gate.
