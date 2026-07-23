# Corotational Fiber-Frame Engineering Recovery

The v1 recovery turns the bounded portal J1-J5 adapter into a typed, hash-bound
engineering result candidate. It starts at the final step's accepted
parent checkpoint, derives terminal generalized coordinates from the committed
physical displacement state, and independently repeats the fixed-profile
corotational assembly transition. Solver-returned force arrays are comparison
evidence and are never used as the recovery source.

The replay must match the terminal assembly and committed element, section, and
constituent state bytes. It also independently checks element scatter, current-chord
local/global force transformation, section integration, fiber strain kinematics,
the internal and external load vectors, the constrained reaction partition, and the
terminal free-equation residual.

## Result quantities

All engineering output uses the hashed Result Quantity Catalog and canonical SI:

| Artifact | Unit |
| --- | --- |
| Node translations / rotations | `m` / `rad` |
| Reaction forces / moments | `N` / `N*m` |
| Current-chord member end forces / moments | `N` / `N*m` |
| Section axial force / moment | `N` / `N*m` |
| Section strain / curvature | `1` / `1/m` |
| Fiber strain / stress | `1` / `Pa` |

Node rows follow compiled node order. Member rows follow compiled member order;
their force components are `[N_i, V_i, N_j, V_j]` and their moment components
are `[MZ_i, MZ_j]` in the member's current chord axes. Section rows follow
member then integration-point order, and fiber rows follow section then authored
fiber order. Offset arrays retain each member-to-section and section-to-fiber
partition.

The object retains immutable byte-backed arrays. Every artifact descriptor binds its
dtype, shape, unit, quantity IDs, deterministic order, exact byte hash, and combined
content hash. The manifest and aggregate array bundle are independently hashed.

## Authority boundary

This is exact engineering recovery only within the bounded one-bay/one-story portal
candidate landed by PR 7. The recovery contract itself remains load-control,
CPU-dense, zero-prescribed-displacement, and excludes member end releases, rigid
offsets, distributed member loads, displacement control, connected/general frame
topology, and public API promotion. The bounded unified API now consumes this
contract as a Developer Preview candidate without changing its underlying
`public_api=not_promoted` authority. It does not establish an external Level 2 comparison,
grant design-code authority, or establish release readiness. A detached manifest
validates strict finite JSON, fixed authority semantics, descriptor shapes/order, and
aggregate hashes. It does not replace the artifact bytes or authenticate the retained
compiler, problem, solver path, or checkpoint objects.

The schema is
`src/structural_analysis/schemas/corotational_fiber_frame_engineering_result_v1.schema.json`;
focused tests are in `tests/test_corotational_fiber_frame_engineering_recovery.py`.

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q \
  tests/test_corotational_fiber_frame_engineering_recovery.py \
  tests/test_corotational_fiber_frame_j1_j5.py
```
