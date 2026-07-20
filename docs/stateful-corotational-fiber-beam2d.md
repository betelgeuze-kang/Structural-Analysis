# Stateful corotational 2D fiber-beam element

## Implemented boundary

`StatefulCorotationalFiberBeam2D` connects the exact current-chord basic
kinematics to the existing stateful axial-curvature fiber-beam integrator. The
element now owns one bounded material-geometric response with

- immutable per-integration-point steel and concrete parent states;
- exact three-mode basic deformation and force mapping;
- algorithmic material and exact geometric tangent contributions;
- finite rigid-motion objectivity;
- committed chord-angle continuity across the principal `atan2` branch;
- canonical element-state bytes and deterministic state hashes.

This is an element boundary, not a multi-element nonlinear frame solver. It
does not yet provide global topology/constraint assembly, a global checkpoint
chain, load control, arc length, persisted restart artifacts, external cyclic
member validation, mesh-objectivity evidence, or G1 closure.

## Kinematic and constitutive chain

For basic deformation

```text
v = [delta, beta_i, beta_j]
  = [l-L, theta_i-dphi, theta_j-dphi],
```

the projection into the existing six-component local beam integrator is

```text
u_basic_local = [0, 0, beta_i, delta, 0, beta_j] = A v.
```

The local beam integrates axial strain and Hermite curvature at each Gauss
point from the same immutable committed section parents. Its local force and
algorithmic tangent are reduced to the basic system as

```text
q  = A.T f_basic_local
kb = A.T K_basic_local A.
```

The current-chord boundary then recovers

```text
f_global    = B.T q
K_material  = B.T kb B
K_geometric = sum(q[a] H[a])
K_consistent = K_material + K_geometric.
```

The response exposes the basic, local section-integration, and global
decomposed quantities together so their ancestry and equation definitions are
auditable.

## Committed angle branch

The stateless kinematic kernel returns the principal chord rotation. For a
trial evaluated from a committed element state, the element adds the integer
multiple of `2*pi` nearest to the committed chord rotation. Half-turn ties use
one deterministic rule toward positive infinity.

This makes sequential rotations beyond `pi` continuous when each accepted
chord-rotation increment stays strictly below `pi`. A single jump of `pi` or
more is physically ambiguous from endpoint coordinates alone and is not
claimed. Nonlinear solution control must subdivide such increments.

## Verification boundary

Focused tests establish

- exact deterministic initial and trial state hashes;
- superposed finite rigid-motion covariance of force and tangent;
- zero-strain sequential rigid rotations through `4.4 rad`;
- nonlinear RC force-Jacobian agreement from one committed parent;
- nonzero material and geometric tangent decomposition;
- cyclic steel-yield/concrete-damage evolution with monotonic dissipation;
- exact replay and rollback-safe unchanged-parent trial behavior;
- response-parent binding, state/kinematic consistency, immutability, and
  fail-closed input handling.

The next E-wave slice is global assembly of these elements with explicit
constraints and committed checkpoint ancestry. P-Delta portal, cyclic member
reference, restart artifacts, and snap-through paths remain later acceptance
gates.
