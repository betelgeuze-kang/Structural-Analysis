# ModelIR Frame3D Uniform Member Distributed Load Linear v1

## Contract

One `linear_static` load pattern may contain an optional ordered
`member_distributed_loads` array. Each row has a stable `id` and `index`, references one
Euler-Bernoulli `frame_3d` element, and is restricted to:

- `basis: initial_member_local`;
- `distribution: uniform_full_span`;
- finite SI components `qx_n_per_m`, `qy_n_per_m`, and `qz_n_per_m`;
- at least one nonzero component.

Partial-span, trapezoidal, global/projected, follower, temperature, moving, point-member,
Truss3D, shell, nonlinear-pattern, and value-inferred forms are not accepted. Unknown wire fields
remain schema errors. Nested load IDs are globally unique across nodal and member-load rows.

The append-only C descriptor keeps the legacy 608-byte `sa_model_ir_descriptor_v1` prefix and adds
one flattened typed sidecar. A descriptor declaring the exact legacy prefix is accepted and cannot
observe the sidecar; a partially declared suffix fails with `SA_ERR_STRUCT_SIZE`. The public ABI
function table remains v1.14 because no operation slot changed.

## Numerical convention

For effective element length `L`, the declared local load `[qx,qy,qz]` produces the consistent
local equivalent nodal vector

```text
[ qxL/2, qyL/2, qzL/2, 0, -qzL²/12,  qyL²/12,
  qxL/2, qyL/2, qzL/2, 0,  qzL²/12, -qyL²/12 ]
```

The effective chord includes finite global rigid offsets. The same initial local-axis rotation,
rigid-arm transform, and nonsingular release condensation operator used by the element stiffness
map the load into global active/constrained equations. Local end-force recovery subtracts the
condensed fixed-end vector, so released force components remain exact zero. Direct and bounded
direct/nested linear-combination factors scale both the external vector and recovery vector.
Reactions retain the established `internal - external` convention.

## Verification

- C++ reference-element tests check the closed-form vector, deterministic repeat, release zero
  forces, and nonfinite rejection.
- Typed ModelIR tests cover active/constrained load projection, fixed-end recovery, unsupported
  Truss3D and all-zero rows, and the legacy root prefix.
- An independent NumPy oracle compares rotated local-to-global loads, signed combination factors,
  reactions, and a three-dimensional rigid-offset plus i-RY/j-RZ release case. The offset/release
  lane compares load-induced deltas, independently reconstructing the effective chord, rigid-arm
  map and `Kqq * Rq = -Kqr` condensation.
- Safe Rust crosses the descriptor sidecar and verifies exact zero-state load, fixed-end force and
  constrained reaction values with CPU fallback 0.
- The source-built CLI and Workbench solve a two-metre cantilever under `qy=-1000 N/m`, recover
  `FY=2000 N` and `MZ=2000 N·m` at the support, match the Euler-Bernoulli
  `qL⁴/(8EI)=-0.0002 m` tip displacement, publish ResultIR/recovery/reaction/report surfaces,
  and produce byte-identical direct and real-checkpoint-resumed artifacts.
- The topology view marks both endpoints of a member carrying a distributed load, preventing an
  operator from seeing an apparently unloaded member.
- Installed static and shared distribution v96 independently author the same request through the
  installed Workbench under an empty `PATH`, execute direct and one-real-iteration/resumed CPU
  products, preserve byte-identical terminal directories, and bind six distinct model, request,
  ResultIR, recovery, reaction and checkpoint identities. The installed fixture retains the exact
  equivalent active load, fixed-end recovery, support reaction and closed-form tip displacement.
- Local rootfs diagnostic v18 repeats the installed product as UID/GID 65532 with an empty `PATH`,
  read-only root and payload, writable operator workspace and loopback-only networking. Its
  self-hashed receipt retains six distinct product identities and the same numerical assertions.

## Authority boundary

This is a bounded source-built, installed static/shared and isolated-rootfs CPU C5
implementation/verification surface. The v96 receipt has `hosted_cpu_c5` authority and v18 has
`local_rootfs_diagnostic_c5` authority only. Neither is an OCI/customer image, independent external
solver validation, a design-code load generator, engineering acceptance, commercial equivalence,
customer publication, or release authority. HIP parity, general member-load shapes/bases, nonzero
prescribed constraints and shell/nonlinear consumption remain open.
