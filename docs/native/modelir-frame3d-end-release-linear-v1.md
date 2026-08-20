# ModelIR Frame3D Linear End Release v1

Status: bounded installed CPU C5 integration evidence; engineering and customer release authority remain open.

## Contract

The typed ModelIR `frame_3d/euler_bernoulli_3d` path consumes unique release labels from each
element end as local `UX, UY, UZ, RX, RY, RZ` components. For the unreleased 12-DOF local elastic
stiffness `K`, released coordinates `q`, and retained coordinates `r`, the native element solves

`Kqq * Rq = -Kqr`.

It builds a 12-by-12 kinematic recovery `C` whose retained rows are identity, whose released rows
contain `Rq`, and whose released nodal columns are zero. If `T` is the existing global-to-local
mapping including any finite rigid offsets, the element uses `C*T` consistently:

- tangent: `(C*T)^T * K * (C*T)`;
- consistent mass: `(C*T)^T * M * (C*T)`;
- residual and JVP: the same condensed global tangent;
- local recovery: `K * (C*T) * u`, with released force components normalized to exact zero.

The mass rule is a bounded Guyan-compatible kinematic condensation using the stiffness-derived
recovery. It is not an independent dynamic release model or a claim of modal validation.

## Numerical boundary

The dense local solve uses scaled partial pivoting and verifies its reassembled residual. It has no
regularization, pseudoinverse, penalty, fallback, or hidden release deletion. Unknown or duplicate
zero-based native components fail before the solve. An all-released set and any singular or
numerically inadmissible `Kqq` block fail closed. In particular, the focused regression rejects a
two-end axial release instead of inventing a recovery for the free internal rigid mode.

An empty release set does not form or multiply an identity recovery matrix; the previous arithmetic
path is retained. The frozen ABI v1.7 direct reference-element descriptor remains zero-release.
ModelIR already carried release arrays through the existing ABI descriptor, so the typed linear
projection and safe Rust v1.13/v1.14 assembly require no ABI extension.

## Verification and product integration

- A general rotated three-dimensional element with nonzero offsets and i-RY/j-RZ releases matches
  an independent NumPy construction for tangent, consistent mass, residual, JVP, and local end
  forces.
- C++ tests cover symmetry, exact-zero released forces, deterministic ModelIR assembly, invalid
  components, and singular-set rejection.
- Safe Rust preserves the exact ModelIR identities, changed operator/recovery values, deterministic
  repeat, CPU backend, and fallback zero.
- A stable constrained cantilever with an i-RY release crosses source-built Workbench
  `Import -> Validate -> Run(1) -> Resume -> Compare -> Report`. Direct and resumed artifact trees
  are byte-identical, and the element-recovery view displays the released i-MY value as exact zero.
- Installed static/shared distribution receipt v94 independently binds the constrained model,
  Workbench-authored request, fallback-free ResultIR, twelve-component recovery, positive
  exact-zero released i-MY, real-iteration checkpoint and direct/resume parity.
- Local rootfs diagnostic v16 repeats that surface as UID/GID 65532 with an empty PATH, read-only
  root and payload, writable operator workspace and loopback-only networking.

## Honest boundary

This is implementation and focused verification evidence, not independent external validation or
customer release authority. The installed v94 and rootfs v16 receipts are local C5 integration
evidence and do not promote engineering acceptance. HIP remains fail-closed for releases. Truss3D releases, singular release mechanisms,
member distributed loads, self-weight, geometric/material nonlinearity, release-aware deformed
shape visualization, design checks, external engineering acceptance, and C6 decommission remain
open.
