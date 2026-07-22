# Stateful corotational fiber-frame global assembly

## Implemented boundary

`StatefulCorotationalFiberFrame2DProblem` connects multiple
`StatefulCorotationalFiberBeam2D` members through shared planar nodal degrees
of freedom `[ux, uy, theta]`. The bounded v1 assembly provides:

- exact member connectivity and element-coordinate binding;
- deterministic global DOF gather/scatter for shared nodes;
- dense global internal-force assembly;
- separate global material and geometric tangent assembly, with the consistent
  tangent defined as their sum;
- fixed-zero constraints, reference nodal loads, reactions, and a
  length-scaled rotational coordinate for a later Newton solver;
- immutable, hash-addressed frame checkpoints that bind global displacements
  to every member's complete corotational/fiber state;
- exact trial-parent binding without mutation of the accepted checkpoint.

The existing small-displacement `StatefulFiberFrame2D` path and its persisted
checkpoint schemas are unchanged. The corotational path uses a separate schema
because its member state additionally owns global element displacements and an
unwrapped committed chord rotation.

## Assembly equations

For member global DOF index map `g_e`, the physical assembly is

```text
f_int[g_e]       += f_e
K_material[g_e]  += K_material,e
K_geometric[g_e] += K_geometric,e
K_consistent      = K_material + K_geometric
r_physical        = f_int - lambda * f_reference
```

The member response already uses exact current-chord kinematics:

```text
f_e = B_e^T q_e
K_e = B_e^T k_basic,e B_e + sum(q_e,a H_e,a)
```

Rotations are converted to length-valued generalized solver coordinates with
`u = S q`. The free-equation residual and Jacobian are therefore

```text
r_generalized = S_free^T r_physical,free
K_generalized = S_free^T K_consistent,free S_free
```

No initial-chord force or tangent transformation is applied in this assembly;
each corotational member already returns its response in the problem's global
axes.

## Checkpoint boundary

`StatefulCorotationalFiberFrame2DCheckpoint` stores:

- problem contract hash, epoch, step, and load factor;
- exact parent checkpoint hash for positive epochs;
- all physical global displacements;
- one complete stateful corotational element state per member;
- domain-separated canonical bytes and a deterministic SHA-256 state hash.

Validation requires the gathered global member displacements to match the
embedded element displacement bytes exactly, including the sign of zero. An
assembly evaluates every trial from one immutable accepted checkpoint and
checks every element response's parent hash. The separate bounded
[`stateful_corotational_fiber_frame2d_solver`](stateful-corotational-fiber-frame2d-newton-load-control.md)
module now owns fixed-target Newton convergence and commit authorization; the
assembly itself remains independent of solution control.

The bounded checkpoint codec serializes and restores the complete accepted
frame state as canonical UTF-8 JSON. The separate
[`stateful_corotational_fiber_frame2d_adaptive`](stateful-corotational-fiber-frame2d-adaptive-continuation.md)
controller persists that checkpoint together with its cumulative adaptive
progress and resumes only after source, problem, hash, canonical-byte, and
equilibrium checks pass.

The separate
[`stateful_corotational_fiber_frame2d_arc_length`](stateful-corotational-fiber-frame2d-arc-length.md)
bridge follows limit-point paths with the same assembly and full-state
transaction. It persists the accepted displacement/load tangent so restart
retains the selected equilibrium branch.

## Focused verification

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q \
  tests/test_stateful_corotational_fiber_frame2d_solver.py \
  tests/test_stateful_corotational_fiber_frame2d_adaptive.py \
  tests/test_stateful_corotational_fiber_frame2d_arc_length.py \
  tests/test_stateful_corotational_linked_frame_cyclic_benchmark.py \
  tests/test_stateful_corotational_local_axis_linked_frame_cyclic_benchmark.py \
  tests/test_stateful_corotational_updated_axis_linked_frame_cyclic_benchmark.py \
  tests/test_stateful_corotational_rotational_linked_frame_cyclic_benchmark.py \
  tests/test_stateful_corotational_composite_frame_cyclic_benchmark.py \
  tests/test_stateful_corotational_concrete_frame_cyclic_benchmark.py \
  tests/test_stateful_corotational_steel_frame_cyclic_benchmark.py \
  tests/test_stateful_corotational_fiber_frame2d.py \
  tests/test_stateful_corotational_fiber_beam2d.py \
  tests/test_corotational_frame2d_basic_kinematics.py
```

The focused tests cover deterministic zero-state assembly, shared-node scatter,
material/geometric tangent decomposition, a same-parent nonlinear global
Jacobian finite difference after RC damage/yield history, sequential 2.2 and
4.4 rad rigid rotations across all members, exact replay, unchanged-parent
trial branching, and fail-closed checkpoint/geometry binding.

The separate
[`stateful-corotational-linked-frame-cyclic-benchmark.md`](stateful-corotational-linked-frame-cyclic-benchmark.md)
case nests the unchanged frame checkpoint with scalar link states, scatters one
free-to-free global-x bilinear link into the full residual and tangent, and
commits both state families atomically. Its 30-target reversal path verifies
force transfer, nonnegative dissipation, same-parent frame-material,
link-material, and geometric tangent terms, deterministic replay, and exact
mixed-state rollback.

The separate
[`stateful-corotational-local-axis-linked-frame-cyclic-benchmark.md`](stateful-corotational-local-axis-linked-frame-cyclic-benchmark.md)
case derives a fixed 45-degree reference direction from an anchor and frame
node, then scatters the scalar response through four global translational DOFs.
It verifies off-axis force and tangent transformation, vector equilibrium,
cyclic link history, replay, and rollback.

The paired
[`stateful-corotational-updated-axis-linked-frame-cyclic-benchmark.md`](stateful-corotational-updated-axis-linked-frame-cyclic-benchmark.md)
case instead uses current length minus reference length, rotates the internal
link force with the current chord, and assembles the force-times-length-Hessian
link geometric tangent separately from the frame geometric tangent. It checks
finite rigid-motion objectivity, current-axis force transformation, full mixed
same-parent tangent, cyclic state, replay, and rollback. General follower
external loads, coupled multi-axis response, shell, contact,
friction, damping, degradation, and general link breadth remain open.

The paired
[`stateful-corotational-rotational-linked-frame-cyclic-benchmark.md`](stateful-corotational-rotational-linked-frame-cyclic-benchmark.md)
case reuses the two-cantilever carrier and 30-target path but connects the two
free top `rz` DOFs. It uses a distinct kN-m/rad material and rotational state,
checks the `S^T K S` generalized-coordinate scaling, common-rotation
objectivity, analytic elastic moment transfer, cyclic dissipation,
same-parent tangent, replay, and rollback. It is one scalar relative-rotation
link, not coupled multi-axis response or general connection breadth.

The separate
[`stateful-corotational-composite-frame-cyclic-benchmark.md`](stateful-corotational-composite-frame-cyclic-benchmark.md)
case places reduced steel-girder and concrete-slab fibers in the same
perfect-bond section. Its 60-target path activates steel plasticity and both
concrete damage branches, tracks constituent dissipation separately, and checks
same-parent mixed-state tangents plus exact rollback. Partial interaction,
connector slip, shear transfer, external composite-member validation, and
general composite breadth remain open.

The separate
[`stateful-corotational-concrete-frame-cyclic-benchmark.md`](stateful-corotational-concrete-frame-cyclic-benchmark.md)
case exercises independent tension and compression damage through the same
30-target reversal path. Concrete supplies more than 75 percent of initial
flexural rigidity, while deliberately elastic reinforcement stabilizes the
post-cracking load-controlled branch. The case verifies componentwise damage
irreversibility, nonnegative dissipation, a two-branch same-parent tangent, and
exact rollback without claiming pure-concrete, mesh-objective, or external
cyclic acceptance evidence.

The separate
[`stateful-corotational-steel-frame-cyclic-benchmark.md`](stateful-corotational-steel-frame-cyclic-benchmark.md)
case exercises isotropic, kinematic, and combined hardening through an internal
30-target reversal path. It keeps concrete carrier fibers elastic, verifies
same-parent yielded tangents and nonnegative steel dissipation, and retains the
external cyclic-member acceptance blocker.

## Claim boundary

This document describes the dense multi-element assembly kernel. Fixed-target
Newton load control and convergence-gated checkpoint acceptance are implemented
in the separate solver boundary linked above. Adaptive load stepping and the
optional spherical arc-length branch both provide cutback, exact rollback, and
persisted single accepted-boundary restart. The combined path still does not
provide prescribed displacements, follower loads, sparse production assembly,
or checkpoint-chain replay. The nearest-branch chord unwrapping remains unique
only when each accepted member rotation increment has magnitude below `pi`.

No authoritative P-Delta portal, Euler-column, external cyclic-member,
snap-through, full-building, or customer-shadow acceptance receipt is supplied
here. G1 and commercial-readiness closure remain open, and protected readiness
evidence is unchanged.
