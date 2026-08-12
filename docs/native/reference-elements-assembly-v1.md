# Bounded Reference Materials, Elements and Assembly v1

Status: CPU C1 slice; aggregate D2/D3 cutover remains partial.

## Scope

This slice moves one deliberately small numerical source into C++20:

- elastic-isotropic `E`, `nu`, density validation and shear-modulus derivation;
- one bilinear uniaxial integration point with explicit next-epoch
  `trial -> commit|rollback` transitions;
- linear 3D truss, 3D Euler-Bernoulli frame and a three-node plane-stress
  membrane embedded in 3D;
- deterministic stable-index dense assembly of tangent, consistent mass,
  residual and JVP.

The three stateless elements compute residual, tangent, JVP and result recovery
from the same element response source. All coordinates and values use SI base
units. The ABI result records CPU execution and fallback count zero.

## Gates

- C0: C++ unit tests cover valid values, degenerate geometry, invalid material,
  duplicate element index, DOF mismatch, out-of-range references and material
  epoch conflicts.
- C1: `tests/test_native_reference_elements_python_parity.py` compiles a
  test-only C++ consumer and compares every matrix/vector value with an
  independent NumPy implementation, including rolled non-axis-aligned frame
  and tilted membrane cases. Python is only the oracle harness and is not
  linked or invoked by native product code.
- ABI integration: ABI v1.7 adds one append-only optional table slot. It uses
  exact-length immutable inputs, disjoint caller-owned outputs, stable errors,
  failure-atomic publication and a reentrant safe Rust wrapper.

C2 is not closed. Consequently, despite the safe ABI wrapper, the capability's
last promotable sequential cutover gate remains C1.

## Explicit boundary

The shell profile is membrane-only. It has no bending, drilling, transverse
shear, nonlinear material, offset, opening or general shell claim. The frame
profile has no rigid offsets, releases, geometric stiffness or nonlinear
constitutive state. Dense assembly is not CSR/sparse assembly and is not an
arbitrary ModelIR operator graph.

Still open: broader formulation/material parity, element-state aggregation,
CSR and constraint assembly, CPU/HIP FP64 C2, resident GPU execution,
checkpoint/restart, ResultIR recovery, product E2E and C6 decommission.
