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
  residual and JVP;
- homogeneous-Dirichlet constraint reduction of the same contributions into a canonical CSR
  active-DOF operator with sorted row columns and explicit global-to-reduced mapping.

The three stateless elements compute residual, tangent, JVP and result recovery
from the same element response source. All coordinates and values use SI base
units. The ABI result records CPU execution and fallback count zero.

## Gates

- C0: C++ unit tests cover valid values, degenerate geometry, invalid material,
  duplicate element index, DOF mismatch, out-of-range references and material
  epoch conflicts. Assembly tests additionally cover reordered contributions and constraints,
  duplicate/out-of-range/all-constrained DOFs, canonical CSR structure, signed-zero normalization
  and non-finite accumulation failure.
- C1: `tests/test_native_reference_elements_python_parity.py` compiles a
  test-only C++ consumer and compares every matrix/vector value with an
  independent NumPy implementation, including rolled non-axis-aligned frame
  and tilted membrane cases. The NumPy oracle independently scatters an irregular three-element
  graph, removes one constrained DOF, constructs the structural pattern and compares the exact
  active mapping, row offsets, column indices, tangent, mass, residual and JVP. Python is only the
  oracle harness and is not linked or invoked by native product code.
- ABI integration: ABI v1.7 adds one append-only optional table slot. It uses
  exact-length immutable inputs, disjoint caller-owned outputs, stable errors,
  failure-atomic publication and a reentrant safe Rust wrapper.

C2 has a product-owned implementation and a successful local live candidate, but is not yet
authoritatively closed. The HIP batch matched all five CPU profiles and their 38-DOF dense
assembly with zero absolute error on a real `gfx1030`, repeated bitwise-identically, retained
operator state on-device between its two kernels and reported fallback zero. The protected
`native-hip-approved` runner receipt is still required, so despite the safe ABI wrapper the
capability's last promotable sequential cutover gate remains C1.

## Explicit boundary

The shell profile is membrane-only. It has no bending, drilling, transverse
shear, nonlinear material, offset, opening or general shell claim. The frame
profile has no rigid offsets, releases, geometric stiffness or nonlinear
constitutive state. The CSR result is a bounded serial reference projection of caller-supplied
local contributions and homogeneous constrained-DOF indices. It does not derive an arbitrary
ModelIR operator graph, apply nonzero prescribed-displacement load corrections, reorder DOFs,
propagate constitutive epochs, cross the Rust FFI, or claim a sparse performance backend.

Still open: protected-runner C2 promotion, broader formulation/material parity,
element-state aggregation, arbitrary ModelIR graph assembly, nonzero constraint handling,
sparse resident execution, Rust FFI, checkpoint/restart, ResultIR recovery, product E2E and C6
decommission.
