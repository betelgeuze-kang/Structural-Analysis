# G1 Real Service Tangent in the Non-Promoting MGT Closure (F2e)

Step F2e of the D→E→F plan. F2d-frame showed the F2b-ii-a / F2c assembled-tangent
decorrelation was an artifact of the smoke closure builder passing
`service_tangent = 1.0 MPa` as a placeholder. F2e wires the **real per-element
service material tangent** into the smoke/audit closure (default) and re-runs the
F2b-ii-a sparse-direct / ILU smoke at the reference state.

It does not change the production solver path, does not regenerate the 0.656
continuation checkpoint, does not promote G1, and writes only untracked
`*.local.json`.

- Closure: `implementation/phase1/run_g1_mgt_physical_line_search_smoke.py`
  (`build_mgt_physical_residual_closure(..., frame_service_tangent_source=...)`,
  default `real_per_element`; `placeholder_1mpa` retained for regression/audit).
- Driver: `implementation/phase1/run_g1_mgt_sparse_direct_physical_line_search_smoke.py`
  (`--frame-service-tangent-source`).
- Tests: `tests/test_g1_real_service_tangent_closure.py` (hermetic).

## Result on the real MGT model (non-promoting local run)

`midas_generator_33.optimized.mgt` (free 51012), `load_scale=0.1`, reference state,
`frame_service_tangent_source=real_per_element` (service tangent stats: min 1e-9,
max ~2.8e10, mean ~3.0e7 MPa):

- **assembled-tangent parity now PASSES** (`cosine ≈ 1.0`, max relative error
  ≈ 1.74e-4) — the placeholder false-negative is removed and the F2d finding is
  confirmed at the full-tangent level;
- `sparse_direct_spsolve`: **`ERR_SPARSE_DIRECT_SOLVE_FAILED`** (SuperLU singular
  pivot, e.g. `dgstrf info` near column ~2887);
- `gmres_ilu`: **`ERR_ILU_FACTOR_FAILED`** (`spilu` hits the same singularity);
- unpreconditioned matrix-free GMRES: `gmres_not_converged_maxiter`.

### Interpretation (partial success; loop closed with the D audit)

The operator-mismatch false-negative is removed: with the real service tangent the
assembled tangent is consistent with the physical residual. The **new bottleneck is
that the raw assembled tangent is singular / rank-deficient** for direct or ILU
factorization at the reference state. This explains *why* the production corrector
applies the λ≈515 regularization named by the D audit: the unregularized assembled
tangent is not factorable, so a regularization is required to obtain a solvable
correction operator.

## Allowed claim after F2e

- "reference-state smoke closure placeholder artifact fixed; assembled tangent is
  consistent with the physical residual under the real service tangent".

## Not claimed (preserved boundaries)

- NOT G1 closed, NOT 0.656 solved, NOT full-load nonlinear equilibrium closed,
  NOT material-Newton breadth closed. The nonlinear-state material reduction
  (`solver_tangent_mpa`) divergence from elastic also remains a separate open
  question.

## Next slice

A principled regularized direction solve (small regularization or zero-energy-mode
pinning on the matrix-free JVP operator / assembled tangent) at the reference
state to obtain an accepted alpha, before any F2b-ii-b continuation. The size of
the regularization needed can be contrasted with the production λ≈515.
