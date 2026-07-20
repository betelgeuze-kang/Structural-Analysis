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
checks every element response's parent hash. This slice does not decide whether
a trial is converged or authorized for commit; that belongs to the next
nonlinear solution-control boundary.

## Focused verification

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q \
  tests/test_stateful_corotational_fiber_frame2d.py \
  tests/test_stateful_corotational_fiber_beam2d.py \
  tests/test_corotational_frame2d_basic_kinematics.py
```

The focused tests cover deterministic zero-state assembly, shared-node scatter,
material/geometric tangent decomposition, a same-parent nonlinear global
Jacobian finite difference after RC damage/yield history, sequential 2.2 and
4.4 rad rigid rotations across all members, exact replay, unchanged-parent
trial branching, and fail-closed checkpoint/geometry binding.

## Claim boundary

This is a dense multi-element assembly kernel, not a nonlinear frame solver. It
does not yet provide convergence-gated checkpoint acceptance, Newton line
search, adaptive load stepping, arc length, prescribed displacements, follower
loads, sparse production assembly, persisted corotational checkpoint artifacts,
or checkpoint-chain replay. The nearest-branch chord unwrapping remains unique
only when each accepted member rotation increment has magnitude below `pi`.

No P-Delta portal, Euler-column, external cyclic-member, restart, snap-through,
full-building, or customer-shadow acceptance receipt is supplied here. G1 and
commercial-readiness closure remain open, and protected readiness evidence is
unchanged.
