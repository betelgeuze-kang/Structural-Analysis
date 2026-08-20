# Bounded ModelIR Linear Self-Weight v1

Status: source-built CPU C5 implementation evidence. This is not installed-distribution,
protected-runner HIP, external engineering-validation, design-code, or release authority.

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

Still open: member distributed-load schema and fixed-end-force semantics, installed static/shared
distribution and read-only rootfs evidence, HIP parity, nonzero prescribed constraints,
shell/nonlinear gravity, independent mass-source engineering validation, design-code load
generation, engineering acceptance, and C6.
