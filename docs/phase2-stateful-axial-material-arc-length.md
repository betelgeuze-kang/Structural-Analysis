# Stateful axial material arc-length bridge

## Outcome

`stateful_axial_material_arc_length_continuation` connects the existing
load-coupled vector arc-length corrector and CPU matrix-free FGMRES tangent
solver to the bounded stateful axial material assembler. It traces a physical
equilibrium path while rebinding each new step to the material state committed
by the preceding accepted step.

The API is intentionally a direct module import:

```python
from structural_analysis.solvers.nonlinear.stateful_axial_material_arc_length import (
    stateful_axial_material_arc_length_continuation,
)
```

It is not re-exported through the nonlinear package initializer because that
initializer is part of retained evidence checksum surfaces unrelated to this
bounded integration.

## Transaction order

Each physical attempt follows this order:

1. validate the accepted displacement and constitutive state hash;
2. bind the residual, current material tangent action, reference
   preconditioner, source problem, and attempted arc length to that immutable
   parent;
3. run exactly one spherical vector arc-length attempt;
4. independently reassemble the converged trial and gate equilibrium residual,
   spherical constraint, monitor direction, linear solve replay, fallback
   count, regularization count, and unchanged parent bytes;
5. atomically create a new `StatefulAxialAcceptedState` from the converged
   displacement, load factor, and trial material states; or
6. retain the original object and exact displacement/material canonical bytes
   before reducing the arc length.

Running only one generic vector attempt per material transaction is essential.
Allowing multiple accepted vector steps under one constitutive parent would
freeze plasticity or damage history across those steps.

## Linearization

The displacement Jacobian action is

```text
assemble(parent, u_accepted + delta_u, lambda_accepted + delta_lambda)
    .jacobian_kn_per_m @ direction_m
```

The augmented corrector uses the physical load-coupled residual. Its load
column is `-partial(residual)/partial(lambda)` and includes both:

- proportional external nodal forces; and
- internal-force derivatives caused by proportional prescribed
  displacements, assembled from the current element consistent tangents.

The focused finite-difference gate checks both the displacement JVP and this
load-factor derivative from the same accepted material parent.

## Checkpoint and restart boundary

Every attempted-step boundary carries:

- the complete `StatefulAxialAcceptedState`, including all bounded material
  states;
- source problem and physical path contract hashes;
- current/reduced arc length;
- previous normalized displacement/load tangent for path orientation;
- cumulative attempt budget; and
- the last commit or rollback outcome.

Restart preserves the cumulative attempt budget and produces the same final
accepted state and checkpoint hash as the uninterrupted run. The object is an
in-memory, material-state-embedded checkpoint. This module does **not** define
a durable serialized artifact format; durable canonical JSON remains the
separate adaptive load-control checkpoint contract.

## Focused evidence

The focused suite covers:

- a two-equation force-controlled concrete-damage chain that passes its peak
  load and follows a descending branch;
- current-tangent CPU FGMRES solves with zero fallback and zero
  regularization;
- exact failed-attempt material rollback before arc-length reduction;
- exact restart from both a rejected boundary and a committed descending-path
  boundary;
- finite-difference agreement for displacement and prescribed-load
  linearizations; and
- committed paths for steel plasticity, concrete damage, composite section,
  and bilinear link material states.

Run it with:

```bash
PYTHONPATH=src python3 -m pytest -q \
  tests/test_stateful_axial_material_arc_length.py
```

## Claim boundary

This bridge establishes bounded axial material path following with explicit
commit/rollback semantics. It does not establish geometric frame/shell
nonlinearity, a Lee-frame benchmark, production-scale sparse Krylov,
ROCm/HIP parity, a durable arc-length checkpoint artifact, or G1 full-building
closure.
