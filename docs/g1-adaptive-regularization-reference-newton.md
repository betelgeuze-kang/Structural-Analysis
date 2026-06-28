# G1 Adaptive Regularization Reference Newton (F2g-3, non-promoting)

Step F2g-3 of the D→E→F plan. F2g-2 showed the reference-state residual plateau is
driven by the fixed regularization (`mu=0.1`), not by tangent staleness. F2g-3 tests
whether an **adaptive** relative-diagonal regularization — greedy per-step selection
of `mu` from a schedule, picking the candidate with the lowest post-line-search
residual — breaks the plateau, versus the fixed `mu=0.1` baseline.

Candidate runner only: no production solver path change, no 0.656 continuation
regeneration, no G1 promotion, no material-Newton-breadth claim. Output is an
untracked `*.local.json`.

- Driver: `implementation/phase1/run_g1_adaptive_regularization_reference_newton.py`
  (`run_adaptive_greedy_newton` testable core; mu candidates are factorized once each
  because the reference tangent is fixed, then solved per step).
- Tests: `tests/test_g1_adaptive_regularization_reference_newton.py` (hermetic).
- Output: `release_evidence/productization/g1_adaptive_regularization_reference_newton.local.json`

## Result on the real MGT model (non-promoting local run)

`midas_generator_33.optimized.mgt` (free 51012), `load_scale=0.1`, real service
tangent, `relative_diagonal_shift`, candidates `[0.1, 0.03, 0.01, 0.003, 0.001,
0.0003, 0.0001, 0.00003, 0.00001]` (all 9 factorable), 12 steps:

- **adaptive does NOT beat the fixed `mu=0.1` baseline**: adaptive final ≈ 47.20 N
  vs fixed-`mu` final ≈ 46.46 N (`beats_fixed_mu_baseline = False`);
- the greedy schedule almost always selects `mu=0.1` (occasionally `0.03`); **no
  candidate below `0.03` is ever selected**;
- per-step evidence (step 0): `mu=0.1 -> 298 N`, `mu=0.01 -> 321 N`,
  `mu=0.001 -> 1777 N`, `mu=1e-5 -> 2223 N` (barely moved from the initial 2232 N):
  smaller `mu` yields a null-mode-limited tiny accepted alpha and a worse residual.

### Key finding (decisive negative result)

Adaptive regularization does not break the plateau. Larger `mu` consistently gives
the best per-step reduction while smaller `mu` is **near-null-mode-limited** (tiny
accepted alpha). Neither large nor small regularization escapes ~46.5 N. The plateau
is therefore **structural — caused by the singular / near-null-space modes of the
assembled tangent — not a `mu`-tuning problem.** This redirects the next lever to a
**zero-energy-mode (null-space) audit / pinning**: regularize or constrain only the
genuine singular modes (mechanisms) instead of the whole diagonal, so the
well-conditioned spectrum can converge.

## Allowed claim

- "at the reference state, greedy adaptive relative-diagonal regularization does not
  beat fixed `mu=0.1`; the residual plateau is structural (near-null-space), not a
  regularization-magnitude problem."

## Not claimed (preserved)

- NOT G1 closed, NOT 0.656 solved, NOT full-load nonlinear equilibrium closed,
  NOT material-Newton breadth closed, NOT residual-gate reached.

## Next slice

F2g-alt — zero-energy-mode (null-space) audit: identify which DOFs/modes drive the
singular pivot(s) (e.g. drilling rotations, unconstrained rotational DOFs, stress-free
geometric-stiffness nulls) and pin only those, instead of a global diagonal shift.
Only after the reference-state residual approaches the gate do F2h lightweight load
continuation and F2b-ii-b 0.656 continuation become appropriate.
