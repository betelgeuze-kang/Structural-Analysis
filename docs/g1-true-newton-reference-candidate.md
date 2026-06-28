# G1 True Newton Reference Candidate (F2g-2, non-promoting)

Step F2g-2 of the D→E→F plan. F2g showed a modified Newton (reference tangent
reused) reduces the physical residual monotonically at the real MGT reference state
but converges linearly and plateaus above the gate. F2g-2 re-linearizes the
regularized assembled tangent at **every** step (true Newton) and contrasts it with
the modified-Newton baseline.

Candidate runner only: no production solver path change, no 0.656 continuation
regeneration, no G1 promotion, no material-Newton-breadth claim. Output is an
untracked `*.local.json`.

- Closure: `build_mgt_physical_residual_closure` now exposes `tangent_rebuild_fn`
  (re-assembles the regularizable free-space tangent at an arbitrary state, with a
  per-state real per-element service tangent).
- Driver: `implementation/phase1/run_g1_true_newton_reference_candidate.py`.
- Tests: `tests/test_g1_true_newton_reference_candidate.py` (hermetic).
- Output: `release_evidence/productization/g1_true_newton_reference_candidate.local.json`

## Result on the real MGT model (non-promoting local run)

`midas_generator_33.optimized.mgt` (free 51012), `load_scale=0.1`, real service
tangent, `relative_diagonal_shift mu=0.1`, 12 steps:

- **true Newton final residual ≈ 46.4562045 N**;
- **modified Newton final residual ≈ 46.4562030 N**;
- the two histories are **identical step by step** (each step `tangent_rebuilt=True`
  and per-step `assembled_tangent_parity=True`), `true_newton_faster_than_modified =
  False`;
- both monotonic; neither reaches the `5e-4 N` gate.

### Key finding (decisive negative result)

Per-step re-linearization does **not** accelerate convergence at the reference
state: the re-linearized tangent `K(u_k)` is effectively identical to `K(u_0)`
because the accepted displacement increments are small and the frame is near-elastic
here, so the tangent is state-insensitive. The convergence **plateau (~46.5 N) is
driven by the fixed regularization (`mu=0.1`, effective shift ≈ 10% of the median
diagonal), not by tangent staleness.** Both modified and true Newton hit the same
regularization-limited plateau.

This redirects the next lever away from re-linearization and toward the
**regularization strategy**: an adaptive `mu` schedule (large `mu` early for big
reduction, small `mu` later for refinement) and/or zero-energy-mode pinning that
regularizes only the singular null space instead of the whole diagonal.

## Allowed claim

- "at the reference state, true (per-step re-linearized) Newton matches modified
  Newton to ~6 significant figures; the residual plateau is regularization-limited,
  not tangent-staleness-limited."

## Not claimed (preserved)

- NOT G1 closed, NOT 0.656 solved, NOT full-load nonlinear equilibrium closed,
  NOT material-Newton breadth closed, NOT residual-gate reached. The per-state
  service tangent is updated (`material_tangent_update.state_updated=true`) but this
  is still the service/regularized tangent, explicitly `not_material_newton_breadth`.

## Next slice

F2g-3: adaptive regularization schedule (`mu = 0.1 -> 0.03 -> 0.01 -> ...`) to drive
the reference-state residual toward the gate; and/or a zero-energy-mode (null-space)
audit so regularization targets only the singular modes. Only after the
reference-state residual approaches the gate does a lightweight load continuation
(F2h) and then F2b-ii-b 0.656 continuation become appropriate.
