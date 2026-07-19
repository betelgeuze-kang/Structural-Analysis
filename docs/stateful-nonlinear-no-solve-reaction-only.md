# Stateful nonlinear `F=0` no-solve contract

A fully constrained prescribed-displacement problem has no free equilibrium
equations. The stateful nonlinear path therefore terminates as
`no_solve_reaction_only`, matching the Engine v2 reduced-CSR disposition.
The receipt constructs and validates an actual fully constrained Engine v2
ExecutionPlan/reduced-CSR identity and binds its `[0]` row pointer, zero free
rows/nonzeros, disabled recurrence flag, and terminal disposition to the
stateful nonlinear result; the alignment is not a hard-coded boolean.

The path performs one zero-equation assembly validation inside the solver
boundary and a direct constitutive/reaction evaluation at the load-step
boundary. A valid step may atomically commit the resulting material state and
reactions, but it does not enter Newton recurrence, solve a linear system, or
run a line search. Residual and increment norms are not applicable, their gates
are `null`, and `convergence_claim` is always `false`.

The bounded receipt covers two prescribed-displacement increments for each of:

- uniaxial asymmetric concrete damage;
- a perfect-bond steel-concrete composite section;
- a bilinear force-deformation link.

For all six steps it requires exact parent/accepted-state hash binding,
constitutive-state change, reaction balance, deterministic replay, zero Newton
iterations, zero linear solves, zero line-search steps, zero regularization, and
zero fallback.

The generic adaptive load controller follows the same terminal policy for an
empty free-displacement vector. It may advance load-factor checkpoints after a
valid zero-equation assembly, while recording no residual/increment gates and
no convergence claim. Invalid zero-equation assembly rolls back exactly and
eventually blocks at its configured minimum step. This generic controller test
does not add material-state or reaction evidence beyond the stateful receipt.

Artifacts:

- `implementation/phase1/release_evidence/productization/stateful_nonlinear_no_solve_reaction_only.json`
- `src/structural_analysis/schemas/stateful_nonlinear_no_solve_reaction_only_v1.schema.json`

Run:

```bash
PYTHONPATH=src python3 scripts/build_stateful_nonlinear_no_solve_reaction_only_artifact.py
PYTHONPATH=src python3 scripts/build_stateful_nonlinear_no_solve_reaction_only_artifact.py --check
PYTHONPATH=src python3 -m pytest -q \
  tests/test_nonlinear_fully_constrained_no_solve.py \
  tests/test_build_stateful_nonlinear_no_solve_reaction_only_artifact.py
```

This receipt does not exercise a free-equation Newton solve and must not be
counted as nonlinear convergence evidence. General frame/shell/material
coupling, full-building equilibrium, G1, production ROCm/HIP parity, external
validation, and release readiness remain outside its claim boundary.

## Non-descent line-search guard

For active free equations, a trial is accepted only when a configured positive
line-search alpha produces strict residual-norm reduction. A rejected search
returns the unchanged state, whose applied increment is zero; that zero must
not satisfy acceptance merely because the increment gate is numerically true.
Adversarial constant-residual scalar and vector probes now fail closed with
`line_search_failed_to_reduce_residual`, `accepted=false`, and no fallback or
regularization.

## Newton configuration guard

`NewtonRaphsonConfig` normalizes supported real scalar types, then rejects
non-finite or non-positive residual/increment tolerances, negative or non-integer
iteration limits, empty/non-positive/non-finite/non-descending backtracking alpha
sequences, and empty backend identifiers. This validation prevents an observed
false PASS where infinite residual and increment tolerances marked the initial
state converged with a nonzero physical residual. A nonempty but unsupported
backend identifier remains a runtime capability guard; a fully constrained
no-solve vector path may ignore it because no backend is invoked.
