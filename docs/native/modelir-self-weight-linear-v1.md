# Bounded ModelIR Linear Self-Weight v1

Status: source-built plus installed static/shared CPU C5 and local rootfs diagnostic evidence.
This is not protected-runner HIP, external engineering-validation, design-code, customer-image,
or release authority.

## Numerical contract

For each selected `linear_static` load pattern, `self_weight` is a finite dimensionless vector in
the ModelIR global frame. C++ multiplies it by standard gravity `9.80665 m/s²`; rotational
accelerations are zero. Each Frame3D or Truss3D contribution is

`equivalent_element_load = consistent_element_mass * global_acceleration`.

The consistent mass is the same deterministic element response used by operator assembly, so
Frame3D global rigid offsets and nonsingular local end releases are already composed into the load.
Resolved direct or nested combination factors multiply acceleration before stable-index element
accumulation. Exact zero self-weight skips this path and preserves the previous nodal-load
arithmetic. Non-finite factor propagation, mass shape drift, multiplication overflow, or
accumulation overflow fails before partial publication.

## Evidence boundary

- C++ tests conserve the fixture's full 40 kg Frame3D-plus-Truss3D mass under global Z gravity and
  require exact repeatability.
- An independent NumPy oracle assembles mass separately and checks active/constrained external
  loads, reactions, and signed combination scaling.
- The safe Rust ABI test fixes a 314 kg cantilever's active FZ/MY load and support reactions with
  CPU fallback 0.
- The source-built CLI converges, publishes recovery and constrained reactions, and resumes an
  initial checkpoint to byte-identical terminal result documents.
- The source-built Workbench completes Import -> Validate -> one-real-iteration Run -> Resume ->
  Compare -> Report. Its external comparison uses the Euler-Bernoulli uniform-load result
  `wL^4/(8EI)` and direct/restarted workspace files are byte-identical.
- Installed static/shared distribution v95 authors the bounded request through the installed
  Workbench and executes the installed CLI in an empty PATH. It binds exact active FZ/MY, support
  FZ/MY, tip UZ, fallback 0, six distinct model/request/ResultIR/recovery/reaction/checkpoint
  identities, and byte-identical direct/resumed fifteen-artifact directories after one real
  iteration.
- Local rootfs diagnostic v17 independently repeats that installed flow as UID/GID 65532 with a
  read-only root and payload, writable operator workspace, empty PATH and loopback-only network.
  Its authority remains `local_rootfs_diagnostic_c5`; no OCI or customer image is produced.

The separate bounded full-span uniform Frame3D member-load path is implemented and verified in
`modelir-frame3d-member-distributed-load-linear-v1.md`; it does not expand this mass-source claim.

Still open: general member-load shapes/bases, HIP parity, nonzero prescribed constraints,
shell/nonlinear gravity, independent mass-source engineering validation,
design-code load generation, engineering acceptance, customer publication, and C6.
