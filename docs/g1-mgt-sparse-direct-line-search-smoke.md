# G1 Assembled-Tangent (Sparse-Direct/ILU) MGT Line-Search Smoke (F2b-ii-a, non-promoting)

Step F2b-ii-a of the D→E→F plan. F2b-i showed diagonal (Jacobi) preconditioning
cannot fix the real MGT model's extreme stiffness-contrast ill-conditioning. This
slice builds the assembled free-space tangent, verifies it against the physical
residual operator (parity vs the matrix-free JVP), and solves the Newton direction
with a sparse-direct factorization or an ILU-preconditioned matrix-free GMRES.

It does not change the default solver path (default solver remains
`gmres_matrix_free`), does not promote G1, does not regenerate the 0.656
continuation checkpoint (F2b-ii-b), and writes only an untracked `*.local.json`.

- Solve helper: `implementation/phase1/g1_assembled_tangent_solve.py`
- Driver: `implementation/phase1/run_g1_mgt_sparse_direct_physical_line_search_smoke.py`
- Tests: `tests/test_g1_mgt_sparse_direct_line_search_smoke.py` (hermetic, synthetic)
- Output: `release_evidence/productization/g1_mgt_sparse_direct_physical_line_search_smoke.local.json`

## Direction solvers (opt-in; default `gmres_matrix_free`)

`gmres_matrix_free`, `gmres_ilu` (matrix-free physical JVP operator preconditioned
by an ILU of the assembled tangent), `sparse_direct_spsolve`, `sparse_direct_splu`.

## Parity guard

Before any assembled-tangent solve, the assembled tangent `K_free` is checked
against the matrix-free physical JVP (`K_free @ v` vs `J_phys . v`). A gross
mismatch fail-closes with `ERR_ASSEMBLED_TANGENT_PARITY_FAILED`.

## Fail-closed reason codes

`PASS`, `ERR_ASSEMBLED_TANGENT_BUILD_FAILED`,
`ERR_ASSEMBLED_TANGENT_SHAPE_MISMATCH`, `ERR_ASSEMBLED_TANGENT_PARITY_FAILED`,
`ERR_SPARSE_DIRECT_FACTOR_FAILED`, `ERR_SPARSE_DIRECT_SOLVE_FAILED`,
`ERR_ILU_FACTOR_FAILED`, `ERR_ILU_GMRES_NOT_CONVERGED`,
`ERR_DIRECTION_SOLVE_BLOCKED`, `ERR_LINE_SEARCH_NO_DESCENT`, `ERR_NAN_RESIDUAL`.

## Observed on the real MGT model (non-promoting local run)

`midas_generator_33.optimized.mgt` (free 51012), `load_scale=0.1`, reference state:

- **`ERR_ASSEMBLED_TANGENT_PARITY_FAILED`**: the assembled free-space tangent is
  **not** the Jacobian of the physical residual. Direct measurement:
  `cosine(K.v, J_phys.v) ≈ 0.02` (decorrelated, not a scale factor; stable across
  finite-difference step sizes), with `||J_phys.v|| ≈ 2.7e12` vs `||K.v|| ≈ 8.2e9`.

### Key F2b-ii-a finding

This is a direct, real-model confirmation of the D-audit operator mismatch: the
assembled tangent (frame material + geometric + shell + springs, as currently
constructed) is essentially decorrelated from the physical residual's directional
derivative. Therefore a sparse-direct / ILU solve of the assembled tangent does
**not** yield a physical-consistent (or even reliably descent) Newton direction —
the parity guard correctly blocks it.

The bottleneck is no longer the linear solver: it is the **reconciliation of the
assembled tangent operator with the physical internal-force / residual model**
(units/scaling, force-based corotational frame linearization, penalty elastic-link
spring contribution). That reconciliation is the required next slice before any
F2b-ii-b continuation work.

## Deferred

- Reconciling the assembled tangent with the physical residual operator (next slice);
- 0.656 continuation checkpoint regeneration/application (F2b-ii-b), which must not
  proceed until the parity gap is resolved.
