# ModelIR Frame3D Prescribed Support Linear CPU v1

Status: bounded source-built CPU C5 implementation and verification. This is not installed-package,
isolated-rootfs, external engineering-validation, release, or customer-acceptance evidence.

## Owned path

This slice executes finite prescribed translations in metres and rotations in radians on DOFs that
are already restrained by a ModelIR v2 `fixed_dofs` constraint. Implicit prescribed values remain
exact zero. C++ projects all restrained `(global_dof, prescribed_value)` pairs into one sorted map,
and every assembly entrypoint requires the supplied full state to match that map exactly while the
direction is zero at constrained DOFs.

For the active partition, Rust initializes the bounded linear product with

```text
effective_rhs = external_active_load - initial_active_internal_force
              = F_a - K_ac u_c
```

The terminal full displacement retains each prescribed constrained value and overlays only the
solved active increment. Recovery and constrained reactions are evaluated at that full state. The
append-only recovery document publishes the exact constrained DOF indices, prescribed values, and
initial active internal force; legacy zero-prescription documents retain their frozen contract.
Terminal verification checks linear superposition between the initial internal force and the
active-direction JVP with a bounded FP64 tolerance instead of incorrectly requiring the two vectors
to be bitwise identical.

## Verification

- Focused C++ tests prove the unchanged tangent/external load, changed internal force and reaction,
  deterministic sorted projection, and fail-closed rejection of a zero placeholder for a nonzero
  prescribed DOF.
- Safe Rust FFI and product tests prove the same boundary, exact checkpoint restart, canonical
  recovery/reaction documents, and rejection of a tampered prescribed-value binding.
- An independent NumPy oracle checks the initial internal force, effective active right-hand side,
  constrained internal force, and reaction.
- A source-built Workbench E2E authors `BC1.UX = 0.001 m`, authors a bounded load combination,
  performs Import -> Validate -> one-real-iteration Run -> Resume -> Compare -> Report, and matches
  the axial cantilever oracle: tip `UX = 0.00105 m` and base reaction `FX = -100000 N`. The staged,
  resumed, and one-shot terminal artifacts are byte-identical with fallback zero.

## Honest boundary

This closes only bounded linear-elastic Frame3D CPU execution for finite values on already restrained
DOFs. It does not add restraints, execute imposed strain or temperature fields, settlement histories,
multi-point constraints, support springs, contact, stages, time dependence, nonlinear constitutive
response, geometric nonlinearity, HIP parity, general Frame2D/shell support settlement, design-code
checks, external commercial-solver validation, engineering acceptance, installed distribution or
rootfs receipts, signing/publication, or C6 decommission.
