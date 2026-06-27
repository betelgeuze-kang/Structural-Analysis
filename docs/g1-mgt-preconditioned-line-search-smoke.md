# G1 Preconditioned Real-MGT Physical Line-Search Smoke (F2b-i, non-promoting)

Step F2b-i of the D→E→F plan. F2a showed that, on the real MGT model, the physical
residual closure and physical-consistent JVP wire up (JVP parity ~2.7e-16) but the
**unpreconditioned** matrix-free Newton direction solve is blocked
(`gmres_not_converged_maxiter`). F2b-i attaches a free-space diagonal (Jacobi)
preconditioner and reports a `none` vs `preconditioned` comparison on the same
real-model reference state.

It does not change the default solver path, does not promote G1, does not
regenerate the 0.656 continuation checkpoint (F2b-ii), and writes only an untracked
`*.local.json`. The default preconditioner is `none`.

- Preconditioner helpers + preconditioned solve: `implementation/phase1/g1_physical_residual_line_search.py`
- Driver: `implementation/phase1/run_g1_mgt_preconditioned_physical_line_search_smoke.py`
- Tests: `tests/test_g1_mgt_preconditioned_line_search_smoke.py` (hermetic, synthetic)
- Output: `release_evidence/productization/g1_mgt_preconditioned_physical_line_search_smoke.local.json`

## Preconditioner modes (opt-in; default `none`)

`none`, `jacobi_diag` (1/diag, sign-preserving, floored), `absolute_jacobi_diag`
(1/max(|diag|, floor)), `damped_jacobi_diag` (1/(max(|diag|, floor) +
damping_ratio*max|diag|)). All applied in free space.

## F2b-i success criterion

Success is **not** full-load closure. Success is a JVP-parity-preserving,
non-promoting comparison that either obtains an accepted alpha or narrows the
linear-solve bottleneck with an explicit `reason_code`.

## Observed on the real MGT model (non-promoting local run)

`midas_generator_33.optimized.mgt` (free 51012), `load_scale=0.1`, reference state:

- JVP parity: **pass**.
- Free-space diagonal spans ~0.024 to ~9.4e11 (condition ~4e13), driven by the
  stiff elastic-link springs (~1e9 N/m scaled by `stiffness_scale_to_si=1000`).
- Direction solve residual inf-norm after a bounded budget:
  - `none` (unpreconditioned): 2232 -> ~71.5 N (400 iters), still not at rtol;
  - `damped_jacobi_diag`: 2232 -> ~430 N (worse);
  - `absolute_jacobi_diag`: 2232 -> ~2676 N (worse).

### Key F2b-i finding

Diagonal (Jacobi) preconditioning does **not** help — and actually **hurts** — on
this model, because the ill-conditioning comes from extreme stiffness *contrast and
coupling* (penalty-like elastic-link springs), which a diagonal scaling cannot fix.
Unpreconditioned GMRES makes the best (but still slow) progress. This narrows the
bottleneck: F2b-ii should use a stronger preconditioner (e.g. ILU on the assembled
tangent) or a sparse-direct solve on the assembled tangent, not Jacobi.

## Deferred to F2b-ii

A stronger/convergent direction solve (ILU or sparse-direct) and, separately, the
0.656 continuation checkpoint regeneration/application.
