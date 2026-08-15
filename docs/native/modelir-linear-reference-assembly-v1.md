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
  and self-weight fail-closed paths.
- C1: `tests/test_native_model_ir_assembly_python_parity.py` compiles a test-only C++ consumer. An
  independent NumPy implementation evaluates a rolled frame and orthogonal truss, scatters their
  18-DOF graph, reduces it to seven active DOFs and 43 structural entries, and compares the exact
  active map, CSR rows/columns, tangent, mass, internal force, direct and combined external load,
  equilibrium residual, JVP, constrained map/load/reaction vectors, and both recovery records.
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

The projection rejects non-linear material or formulation state, frame2d, shell, rigid offsets,
end releases, member loads, nonzero prescribed constraints, self-weight, direct combinations
outside two through 64 unique linear-static patterns, nested combinations deeper than eight or
larger than 64 expanded leaves, cancellation below two resolved patterns, non-finite/zero factors,
time functions, construction stages, and declared unsupported features. It does not solve the
assembled operator by itself, add reactions to the frozen ABI v1.13 operation, reorder DOFs, or
propagate constitutive epochs; reaction projection is available only through ABI v1.14.
The separate bounded composition in `modelir-linear-product-e2e-v1.md` now feeds this exact output
to the existing CPU PCG product, wraps its real iteration state in a ModelIR-bound C4 checkpoint,
and publishes C5 ResultIR/ReportIR plus active-DOF and element recovery. That separate capability
does not promote this numerical family past C1.

Still open: those excluded formulations and general load semantics, shell graph support, stateful
trial/commit/rollback aggregation, product/restart publication of the ABI v1.14 reaction vectors,
authoritative sequential C2/C3 promotion, durable job/service integration for this profile, and C6
decommission.
