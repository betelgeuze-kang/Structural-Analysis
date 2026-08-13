# Bounded ModelIR Linear Reference Assembly v1

Status: CPU C1 numerical slice only; no ABI, Rust product, solver, or HIP promotion.

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
- projects the selected nodal loads into the same active order and emits both external load and
  `equilibrium_residual = internal_force - external_load`;
- carries the exact ModelIR content, semantic, and provenance hashes plus selected load-pattern
  identity into the pointer-free result.

The request owns exact-length finite full-state and direction vectors. Every constrained entry in
both vectors must be zero. The result is pointer-free C++ storage; no Python or Rust code is linked
or invoked by this target.

## Gates

- C0: `structural_model_ir_assembly_cpu_tests` covers the mixed frame/truss graph, exact active and
  CSR structure, repeated byte-value determinism, load/residual convention, element recovery, bad
  selector and state lengths, nonzero constrained state, rigid offset, nonzero prescribed value,
  and self-weight fail-closed paths.
- C1: `tests/test_native_model_ir_assembly_python_parity.py` compiles a test-only C++ consumer. An
  independent NumPy implementation evaluates a rolled frame and orthogonal truss, scatters their
  18-DOF graph, reduces it to seven active DOFs and 43 structural entries, and compares the exact
  active map, CSR rows/columns, tangent, mass, internal force, external load, equilibrium residual,
  JVP, and both recovery records.

This advances only the bounded D3 CPU reference slice. The sequential gate remains C1 because no
protected HIP C2 receipt exists for this typed graph path, and the path has no stable ABI or Rust
integration.

## Fail-closed boundary

The projection rejects non-linear material or formulation state, frame2d, shell, rigid offsets,
end releases, member loads, nonzero prescribed constraints, self-weight, load combinations, time
functions, construction stages, and declared unsupported features. It does not solve the assembled
operator, compute reactions, reorder DOFs, propagate constitutive epochs, expose an ABI, create a
checkpoint, publish ResultIR, or claim sparse-performance or product authority.

Still open: those excluded formulations and load semantics, shell graph support, stateful
trial/commit/rollback aggregation, ABI C3, restart C4, product E2E C5, protected HIP C2, and C6
decommission.
