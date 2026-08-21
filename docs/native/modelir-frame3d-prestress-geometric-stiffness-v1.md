# ModelIR Frame3D Prestress Geometric Stiffness v1

## Claim boundary

This slice is a bounded C1 numerical foundation for ModelIR linear buckling. It is not a complete
ModelIR buckling analysis, ResultIR product, Workbench workflow, distribution claim, engineering
validation, or PM-1 closure.

The operation accepts one immutable typed ModelIR and one full global displacement vector that is
already the exact equilibrium for a selected linear-static pattern or bounded combination. It
returns only the active-DOF geometric stiffness operator and per-frame reference compression.

## Numerical convention

The generalized eigenproblem is

`K phi = lambda Kg phi`.

Compression is positive and produces a positive-semidefinite `Kg`. For each Frame3D bending plane,
the local consistent beam-column contribution is

`P / (30 L) * [[36, 3L, -36, 3L], [3L, 4L^2, -3L, -L^2], [-36, -3L, 36, -3L], [3L, -L^2, -3L, 4L^2]]`.

The local-z/RY plane uses the corresponding rotation-sign convention. The existing Frame3D
local-axis, finite global rigid-offset and nonsingular end-release mappings transform the operator;
the deterministic assembly layer then emits the same sorted active-DOF map and canonical CSR
topology used by elastic assembly.

## Fail-closed profile

The operation rejects:

- any non-Frame3D element;
- nonzero prescribed restraint values;
- member distributed loads or self-weight in the selected prestress source;
- invalid, nonfinite, or active-equilibrium-violating displacements;
- unbalanced element axial end forces, tensile prestress, or a graph with no positive compression;
- malformed, aliased, overlapping, undersized, non-host, or wrong-version ABI buffers.

No caller output or result descriptor is mutated unless the entire calculation succeeds. Fallback
is always zero.

## ABI and ownership

ABI v1.15 appends one function pointer at byte offset 216 and expands the table to 224 bytes. ABI
v1.14 retains its frozen 216-byte prefix, null slot and clear capability bit. The operation reuses
the immutable v1.13 exact-size query and writes nine disjoint caller-owned buffers. The Rust wrapper
owns those buffers and independently validates counts, CSR ordering, finite values, sorted frame
indices, nonnegative compression with at least one positive member, backend/fallback metadata and
all three ModelIR identities before publishing a safe result.

## Verification

- direct Frame3D element tests lock the standard matrix, symmetry, rigid-offset/end-release
  transformation and tensile rejection;
- direct ModelIR tests lock exact equilibrium recovery, canonical CSR and non-equilibrium/tension
  failures;
- the C ABI contract test locks v1.14 prefix compatibility, v1.15 capability/slot negotiation,
  exact outputs and failure atomicity;
- the Rust integration test locks safe ownership, identity preservation and old-table rejection;
- the Python/NumPy parity lane independently reconstructs the cantilever matrix and compares every
  canonical CSR value.

## Remaining integration work

The existing bounded dense generalized-eigen buckling solver is still a separate matrix-level
capability. A later slice must bind elastic `K`, prestress `Kg`, request identity, eigen controls,
checkpoint, ResultIR, report, Workbench session and release evidence without weakening either
component's current authority boundary.
