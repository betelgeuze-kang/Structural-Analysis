# Corotational Fiber-Frame Engineering Recovery

The v1 recovery turns the bounded portal or connected-frame J1-J5 adapter into a typed,
hash-bound engineering result candidate. It starts at the final step's accepted
parent checkpoint, derives terminal generalized coordinates from the committed
physical displacement state, and independently repeats the full corotational
assembly transition, including member end releases, rigid offsets, and member dead loads.

The replay must match the terminal assembly and committed element, section, and
constituent state bytes. It also independently checks element scatter, current-chord
local/global force transformation, section integration, fiber strain kinematics,
the internal and external member scatter, released-end net-moment equilibrium, the
constrained reaction partition, and the terminal free-equation residual.

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

The object retains immutable byte-backed arrays. Every artifact descriptor binds its
dtype, shape, unit, quantity IDs, deterministic order, exact byte hash, and combined
content hash. The manifest and aggregate array bundle are independently hashed.

## Authority boundary

This is exact engineering recovery within the bounded portal and connected-frame
candidates. It covers only the RZ/global-XY/uniform-dead-load member-feature profile;
it does not establish an external Level 2 comparison, grant design-code authority, or
establish release readiness. A detached manifest validates contract shape and hashes
but does not replace the artifact bytes.

The schema is
`src/structural_analysis/schemas/corotational_fiber_frame_engineering_result_v1.schema.json`;
focused tests are in `tests/test_corotational_fiber_frame_engineering_recovery.py`.
