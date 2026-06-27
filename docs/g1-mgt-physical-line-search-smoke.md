# G1 Real-MGT Physical Line-Search Smoke (F2a, non-promoting)

Step F2a of the D→E→F plan. Checks whether the opt-in physical-consistent global
Newton operator and physical-residual line-search preview can be **wired up against
a real MGT model** (not the F1 representative system), in a fail-closed,
non-promoting form. It does not change the default solver path, does not promote
G1, and does not regenerate tracked evidence.

F2a is **not** a 0.656 breakthrough and does **not** regenerate the 0.656
continuation checkpoint — that is F2b.

- Driver: `implementation/phase1/run_g1_mgt_physical_line_search_smoke.py`
- Tests: `tests/test_g1_mgt_physical_line_search_smoke.py` (hermetic, synthetic)
- Output: `release_evidence/productization/g1_mgt_physical_line_search_smoke.local.json`
  (untracked `*.local.json`; never promoted, never committed)

## What it does

Builds a reduced free-space physical residual closure from a real MGT model at a
lightweight reference state and attempts, fail-closed at each step:

1. physical residual evaluation (finiteness + shape contract);
2. matrix-free physical-consistent JVP + parity;
3. a bounded matrix-free Newton direction solve + physical-residual line-search.

Every failure mode returns an explicit machine-readable `reason_code` instead of
crashing:

`PASS`, `ERR_MGT_INPUT_MISSING`, `ERR_MGT_STATE_BUILD_FAILED`,
`ERR_PHYSICAL_RESIDUAL_CLOSURE_FAILED`, `ERR_JVP_PARITY_FAILED`,
`ERR_LINE_SEARCH_NO_DESCENT`, `ERR_MEMORY_BUDGET_EXCEEDED`, `ERR_NAN_RESIDUAL`,
`ERR_OPERATOR_SHAPE_MISMATCH`, `ERR_DIRECTION_SOLVE_BLOCKED`.

## F2a success criterion

Success is **not** forced descent. Success is that the real-model run leaves an
honest, machine-readable, non-promoting report of what worked and what is blocked.

## Observed on the real MGT model (non-promoting, local run)

Model `midas_generator_33.optimized.mgt` (nodes 11355, elements 12728, dof 68130,
free 51012), `load_scale=0.1`, reference state:

- physical residual closure: **built**;
- physical-consistent JVP parity: **pass** (max relative error ~2.7e-16,
  lambda excluded);
- matrix-free Newton direction solve: **blocked** —
  `ERR_DIRECTION_SOLVE_BLOCKED` / `gmres_not_converged_maxiter` (unpreconditioned
  GMRES does not converge at this scale within the bounded iteration budget).

This is the key F2a finding: the operator and JVP wire up correctly on the real
model, but the matrix-free direction solve needs preconditioning (or a different
linear solver) to be usable — a concrete input to F2b.

## Deferred to F2b

Real 0.656 continuation checkpoint regeneration/application, and a preconditioned
or otherwise convergent direction solve at full scale.
