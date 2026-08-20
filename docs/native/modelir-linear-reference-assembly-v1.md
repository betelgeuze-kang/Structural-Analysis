# Bounded ModelIR Linear Reference Assembly v1

Status: CPU numerical gate C1; ABI v1.13 active-system and ABI v1.14 constrained-reaction Rust C3
integration candidates implemented without sequential promotion, product solver authority, or HIP
promotion.

## Owned path

`structural_model_assembly` composes the existing typed C++ ModelIR owner, reference material and
element sources, and deterministic CSR assembler. For one explicitly selected linear-static load
pattern it:

- requires a semantically valid and analysis-ready ModelIR v2 handle;
- maps canonical node index `n` and component `d` to global DOF `6*n + d`, with `d=0..5` for
  `UX, UY, UZ, RX, RY, RZ`;
- resolves every linear-elastic Euler-Bernoulli frame3d or linear truss3d element from typed nodes,
  material, section, and local-axis data;
- evaluates tangent, consistent mass, internal force, JVP, and recovery from each element's one
  reference response source;
- removes homogeneous constrained DOFs, then emits the sorted active map and canonical CSR
  structure with structural zero entries retained;
- projects the selected direct nodal loads, one bounded two-through-64-pattern signed direct
  combination, or one acyclic nested linear combination with root-inclusive depth at most eight,
  at most 64 expanded leaf contributions and two through 64 resolved nonzero unique patterns, into the
  same active order and emits both external load and
  `equilibrium_residual = internal_force - external_load`;
- converts each selected pattern's dimensionless global `self_weight` vector to translational
  acceleration with standard gravity `9.80665 m/s²`, multiplies the exact offset/release-aware
  element consistent mass by that acceleration, and applies the resolved direct or nested
  combination factor before deterministic stable-element accumulation;
- converts each selected pattern's bounded full-span uniform initial-local Frame3D member load to
  consistent global equivalent nodal load through the same effective chord, rigid-arm and release
  mapping, and subtracts the condensed fixed-end vector from local element recovery;
- preserves constrained DOFs in sorted global order and emits constrained internal force,
  constrained external load, and `reaction = internal_force - external_load` from the same
  stable-order element accumulation;
- carries the exact ModelIR content, semantic, and provenance hashes plus selected legacy
  load-case identity into the pointer-free result.

The request owns exact-length finite full-state and direction vectors. Every constrained entry in
both vectors must be zero. The composition target itself returns pointer-free C++ storage and does
not link Python or Rust.

## Gates

- C0: `structural_model_ir_assembly_cpu_tests` covers the mixed frame/truss graph, exact active and
  CSR structure, repeated byte-value determinism, load/residual convention, element recovery, bad
  selector and state lengths, nonzero constrained state, rigid offset, nonzero prescribed value,
  self-weight total-force conservation, deterministic repeat, and numerical fail-closed paths.
- C1: `tests/test_native_model_ir_assembly_python_parity.py` compiles a test-only C++ consumer. An
  independent NumPy implementation evaluates a rolled frame and orthogonal truss, scatters their
  18-DOF graph, reduces it to seven active DOFs and 43 structural entries, and compares the exact
  active map, CSR rows/columns, tangent, mass, internal force, direct and combined external load,
  self-weight and self-weight-combination loads from an independent mass-times-acceleration
  calculation, rotated member loads plus combination scaling, an offset/release member-load delta
  from an independently reconstructed condensation operator, equilibrium residual, JVP,
  constrained map/load/reaction vectors, and both recovery records.
- C3 integration candidate: ABI v1.13 preserves the complete 184-byte v1.12 prefix and appends an
  immutable exact-sizes query plus a failure-atomic execute slot. Execute requires 16 disjoint
  caller-owned host buffers and publishes active/CSR/operator/load/residual/JVP/recovery data and
  all three ModelIR identities only after complete success. Public C/C++ layout smoke, stale-handle,
  pointer/stride/length/alias, exact-size, concurrent immutable and failure-atomic tests cover the
  boundary. `structural-ffi` preserves and validates the 200-byte v1.13 prefix, performs bounded sizes-to-allocation,
  revalidates canonical CSR, recovery offsets, finite values, CPU/fallback metadata and exact model
  identities plus the selected legacy load-case stable index, and has deterministic/concurrent Rust
  integration coverage. Public bounds cap global DOFs and recovery records at 1,000,000 and
  structural entries at 100,000,000 on both sides of the ABI. The nightly bounded
  libFuzzer target mutates both size and execute descriptors, every output-view metadata family,
  safe aliases and numerical inputs while asserting that every rejected call leaves all caller
  output and result bytes unchanged.
- C3 constrained-reaction integration candidate: ABI v1.14 preserves the complete 200-byte v1.13
  prefix and appends exact-sizes plus failure-atomic execute slots for seven disjoint caller-owned
  buffers. The operation reuses the same immutable stable-order element source and returns sorted
  constrained global indices, constrained internal/external load, `internal - external` reactions,
  three ModelIR identities, CPU backend and fallback 0. The 216-byte safe Rust table performs
  bounded allocation and independently revalidates all of those invariants. C/C++ boundary tests
  cover layout, older-minor null slots, exact sizes, short/oversized/aliased buffers, failure
  atomicity, stale handles and concurrent immutable calls; Rust integration tests cover
  deterministic axial support recovery, selector/state rejection and concurrent reads.

This advances only the bounded D3 CPU reference slice. The sequential gate remains C1 because no
protected HIP C2 receipt exists for this typed graph path. The v1.13/v1.14 Rust work is therefore
an implemented C3 integration candidate, not a promoted sequential C3 gate.

## Fail-closed boundary

The projection accepts finite global rigid-end offsets for Euler-Bernoulli Frame3D only and applies
the same effective-endpoint plus rigid-arm mapping to stiffness, mass, residual, JVP and local
end-force recovery. General nonzero 3D offsets match an independent NumPy operator oracle, while
exact zero offsets retain the previous arithmetic path. For Frame3D, unique local end-release DOFs
are admitted only when the released `Kqq` block passes a no-fallback pivot and residual gate. The
same recovery mapping condenses stiffness and mass, released local end forces publish as exact zero,
and a rotated offset plus i-RY/j-RZ release matches the independent NumPy oracle. Singular release
sets fail closed. Truss3D offsets and releases fail closed. Full-span uniform
`initial_member_local` Frame3D qx/qy/qz rows are admitted through the typed append-only root
sidecar; partial/trapezoidal/global/projected/follower/thermal/moving/point-member forms and
Truss3D or nonlinear member loads fail closed. The projection otherwise rejects non-linear
material or formulation state, frame2d, shell, nonzero prescribed constraints, direct combinations
outside two through 64 unique linear-static patterns, nested combinations deeper than eight or
larger than 64 expanded leaves, cancellation below two resolved patterns, non-finite/zero factors,
time functions, construction stages, and declared unsupported features. It does not solve the
assembled operator by itself, add reactions to the frozen ABI v1.13 operation, reorder DOFs, or
propagate constitutive epochs; reaction projection is available only through ABI v1.14.
The separate bounded composition in `modelir-linear-product-e2e-v1.md` now feeds this exact output
to the existing CPU PCG product, wraps its real iteration state in a ModelIR-bound C4 checkpoint,
and publishes C5 ResultIR/ReportIR plus active-DOF and element recovery. That separate capability
also publishes the ABI v1.14 constrained vectors as a self-hashed reaction ResultIR through exact
direct/restart, durable job/service, Workbench, installed distribution v84 and rootfs diagnostic
v7 bindings without promoting this numerical family past C1. Installed distribution v85 and
rootfs diagnostic v8 separately bind the read-only constrained-reaction view without expanding
that numerical authority.

Still open: those excluded formulations and broader member-load semantics, shell graph support, stateful
trial/commit/rollback aggregation, nonzero prescribed-constraint reactions, authoritative
sequential C2/C3 promotion, approved protected-runner HIP C2, engineering acceptance, and C6
decommission.
