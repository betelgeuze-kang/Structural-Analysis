# G1 Regularized Reference Newton Candidate (F2g, non-promoting)

Step F2g of the D→E→F plan. F2f showed a moderate relative-diagonal regularization
(`mu=0.1`) makes the consistent assembled tangent factorable and yields a full-step
(`alpha=1.0`), ~87% residual-reduction physical-residual descent direction at the
real MGT reference state. F2g asks whether a regularized physical-consistent Newton
iterate reduces the physical residual **over multiple steps** (convergence), not
just once.

Candidate runner only: no production solver path change, no 0.656 continuation
regeneration, no G1 promotion. Output is an untracked `*.local.json`. It uses a
modified-Newton scheme (the regularized reference tangent is factorized once and
reused; the physical residual is re-evaluated each step).

- Driver: `implementation/phase1/run_g1_regularized_reference_newton_candidate.py`
  (`run_multistep_newton` testable core + real-MGT orchestration).
- Tests: `tests/test_g1_regularized_reference_newton_candidate.py` (hermetic).
- Output: `release_evidence/productization/g1_regularized_reference_newton_candidate.local.json`

## Result on the real MGT model (non-promoting local run)

`midas_generator_33.optimized.mgt` (free 51012), `load_scale=0.1`, real service
tangent, `relative_diagonal_shift mu=0.1` (effective shift ≈ 6.4e8):

- **multi-step convergence confirmed**: residual decreases **monotonically** over
  the iterations;
  - 8 steps: `2232 → 55.5 N`, total reduction ≈ **0.975**;
  - 20 steps: `2232 → 37.7 N`, total reduction ≈ **0.983**, still monotonically
    decreasing;
- first step is a full Newton step (`alpha=1.0`, ~87% reduction); per-step reduction
  then decays (tail ~1–2% per step);
- the `5e-4 N` residual gate is **not** reached within these step counts.

### Interpretation (good but bounded)

F2g answers its core question affirmatively for the early/multi-step regime: the
regularized physical-consistent reference operator drives a **monotonic** physical
residual reduction across many steps, not just one. However, because this is a
**modified-Newton** scheme (the reference tangent is reused, not re-linearized at
the deformed state), convergence is **linear and slows**, plateauing well above the
gate. Reaching the gate would require full per-step re-linearization (true Newton,
quadratic convergence) or an adaptive regularization schedule.

## Allowed claim

- "at the reference state, the regularized physical-consistent (modified) Newton
  reduces the physical residual monotonically over multiple steps (≈98% over 20
  steps); the residual gate is not reached at the modified-Newton linear rate."

## Not claimed (preserved)

- NOT G1 closed, NOT 0.656 solved, NOT full-load nonlinear equilibrium closed,
  NOT material-Newton breadth closed, NOT residual-gate reached. Results are at the
  `u=0` reference state, `load_scale=0.1`; the nonlinear-state material reduction
  remains a separate open question.

## Next slice

Full per-step re-linearization (true Newton; rebuild the regularized tangent at each
state) or an adaptive regularization schedule to drive the reference-state residual
to the gate — and only then a lightweight load continuation (F2h), before any
F2b-ii-b 0.656 continuation regeneration. If re-linearization re-encounters a
singular/stall pattern, the zero-energy-mode (null-space) audit becomes the priority.
