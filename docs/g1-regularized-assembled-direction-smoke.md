# G1 Regularized Assembled-Tangent Direction Smoke (F2f, non-promoting)

Step F2f of the D→E→F plan. F2e established that, with the real per-element service
tangent, the assembled free-space tangent is consistent with the physical residual
(parity pass) but singular for direct factorization. F2f sweeps a principled
regularization, solves the regularized direction, runs a physical-residual
line-search preview, and quantifies how small a regularization is needed relative
to the production `lambda ~= 515`.

Not a fix and not a closure: no production solver path change, no 0.656 continuation
regeneration, no G1 promotion. Output is an untracked `*.local.json`.

- Helpers: `implementation/phase1/g1_regularized_direction.py`
- Driver: `implementation/phase1/run_g1_mgt_regularized_assembled_direction_smoke.py`
- Tests: `tests/test_g1_regularized_assembled_direction_smoke.py` (hermetic)
- Output: `release_evidence/productization/g1_mgt_regularized_assembled_direction_smoke.local.json`

## Regularization modes (default `none`)

`none`, `scalar_shift` (`K + mu*I`), `relative_diagonal_shift`
(`K + mu*median(|diag|)*I`). A candidate whose direction collapses onto the
negative residual (cosine > 0.98) is flagged `regularization_too_large`.

## Result on the real MGT model (non-promoting local run, Case A)

`midas_generator_33.optimized.mgt` (free 51012), `load_scale=0.1`,
`real_per_element` service tangent; assembled-tangent parity PASS:

- **unregularized: singular** (`ERR_UNREGULARIZED_TANGENT_SINGULAR`);
- **minimum regularization for solvability is tiny** and far below `lambda ~= 515`:
  - `scalar_shift` ≈ 0.001 already factorizes (~5e5x smaller than 515);
  - `relative_diagonal_shift` `mu=1e-9` (effective shift ≈ 6.45) factorizes
    (~80x smaller than 515) with a pure-Newton direction (cosine with -R ~ 1.8e-4);
- **direction quality has a sweet spot** (relative_diagonal_shift sweep):
  - tiny shift (`mu=1e-9`): accepted alpha ≈ 9.77e-4, reduction ≈ 1e-3 (true Newton
    but near-null-mode-limited);
  - `mu=0.1` (effective ≈ 6.4e8): **accepted alpha = 1.0, residual reduction ≈ 0.87**
    (best Newton step);
  - very large shifts (`mu` toward/above the 515 scale, cosine with -R → 1):
    collapse toward gradient descent, reduction drops, flagged
    `regularization_too_large`.

### Interpretation (Case A)

A regularization far smaller than the production `lambda ~= 515` already restores
solvability, and a moderate relative-diagonal shift yields a full-step (alpha=1.0),
~87% residual-reduction Newton direction at the reference state. This quantitatively
supports the D-audit stall insight: the production regularization is well above the
minimum needed for solvability, and direction quality depends strongly on the
regularization scale (too small → near-null-mode-limited tiny steps; too large →
gradient collapse). The reference-state operator now admits a healthy Newton step.

## Allowed claim

- "at the reference state, a small/moderate regularization of the (consistent)
  assembled tangent yields a factorable, full-step physical-residual descent
  direction; the required regularization is far below the production lambda".

## Not claimed (preserved)

- NOT G1 closed, NOT 0.656 solved, NOT full-load nonlinear equilibrium closed,
  NOT material-Newton breadth closed. Results are at the `u=0` reference state; the
  nonlinear-state material reduction remains a separate open question.

## Next slice

A reduced-regularization physical Newton candidate carried over multiple steps /
toward load continuation (still non-promoting), and/or a zero-energy-mode audit of
the singular null space — before any F2b-ii-b continuation regeneration.
