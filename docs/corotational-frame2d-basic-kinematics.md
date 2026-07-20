# Corotational 2D frame basic-deformation boundary

## Status and scope

The stateless planar corotational boundary in
`structural_analysis.elements.corotational_frame2d_basic` is implemented and
covered by analytic-versus-centered-difference tests. It extracts exact
current-chord kinematics from the existing elastic frame kernel so that a
future stateful section or element law can supply basic forces without
duplicating global transformation logic.

This is an implementation boundary, not a stateful corotational fiber-frame
claim. It does not yet provide section-history commit/rollback, multi-turn
rotation unwrapping, global assembly, load control, arc length, cyclic RC
validation, or G1 closure.

## Public contract

The global element degree-of-freedom order is

```text
[ux_i, uy_i, theta_i, ux_j, uy_j, theta_j]
```

For initial chord length `L`, current chord length `l`, and principal chord
rotation change `dphi`, the basic deformation order is

```text
v = [l - L, theta_i - dphi, theta_j - dphi].
```

`corotational_frame2d_basic_kinematics(...)` returns immutable arrays for

- `v`,
- its exact global gradient `B = dv/du`, and
- its three exact global Hessians `H[a] = d²v[a]/du²`.

A constitutive response satisfies `Frame2DBasicConstitutiveResponse` when it
provides a three-component conjugate force vector `q` and a finite `3 x 3`
algorithmic tangent `kb`. The recovery function then evaluates

```text
f_global = B.T q
K_material = B.T kb B
K_geometric = sum(q[a] H[a])
K_consistent = K_material + K_geometric.
```

The elastic `corotational_frame2d_response(...)` now uses this same boundary;
its existing result type, units, error behavior, energy, force, and tangent
semantics are unchanged.

## Rotation branch boundary

The chord rotation change is the principal `atan2` difference. Derivatives are
valid on a continuous local solution path away from its branch cut. A rigid
rotation within that branch produces zero basic deformation. Rotations beyond
the branch are intentionally not unwrapped: robust multi-turn behavior needs
an accepted/committed angle history and belongs to the future stateful
corotational element.

## Verification boundary

The focused tests cover

- exact first derivatives against centered differences;
- exact second derivatives against the gradient Jacobian;
- finite rigid translation and rotation;
- the documented principal-angle branch behavior;
- elastic force/tangent parity after the refactor;
- material/geometric tangent decomposition;
- immutable, finite, shape-checked public results.

P-Delta portal response, cyclic RC member response, state restart/replay, and
snap-through validation remain acceptance requirements for later E-wave
slices.
