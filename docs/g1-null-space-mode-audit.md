# G1 Null-Space Mode Audit (F2g-alt, non-promoting)

Step F2g-alt of the D→E→F plan. F2g-3 showed the reference-state residual plateau is
structural (near-null-space), not a regularization-magnitude problem. This audit
identifies which free DOFs / modes drive the singular / near-null space of the
assembled tangent, maps them to node / DOF types, and **proposes (does not apply)**
pinning candidates.

Audit only: no pinning applied, no production solver path change, no 0.656
continuation regeneration, no G1 promotion. Output is an untracked `*.local.json`.

- Helpers: `implementation/phase1/g1_null_space_audit.py`
- Driver: `implementation/phase1/run_g1_null_space_mode_audit.py`
- Tests: `tests/test_g1_null_space_mode_audit.py` (hermetic)
- Output: `release_evidence/productization/g1_null_space_mode_audit.local.json`

## Method

Diagonal zero/tiny scan + unregularized factorization singularity check + smallest
eigenpairs via shift-invert `eigsh(K_free, k, sigma=-1.0)` (so `K - sigma I` is
factorable). Each near-null eigenvector is mapped to dominant DOF types (energy
`z^2` grouped by `UX/UY/UZ/RX/RY/RZ`) and top nodes, then classified
(drilling / unrestrained-rotation / translation / distributed).

## Result on the real MGT model (non-promoting local run)

`midas_generator_33.optimized.mgt` (free 51012), `load_scale=0.1`, real service
tangent, 8 modes:

- unregularized factorization: **singular**; diagonal spans ~24.6 to ~8e14
  (no exact-zero diagonals);
- the 8 smallest eigenvalues are all **marginally NEGATIVE** (≈ −1.6e-7 to −7.0e-7)
  → the assembled tangent is **indefinite**, not merely singular;
- the near-null modes are **translation/rotation (rigid-body-like) mechanisms**:
  mode dominant types include `UY ≈ 0.90`, `UX ≈ 0.87`, `UZ ≈ 0.62`, `RY ≈ 0.68`;
  **none are drilling (RZ) dominated**;
- pinning candidates are **distributed** across `UY / RY / UZ / UX` (no single clean
  mechanism type).

### Key finding (Case C: distributed / indefinite)

The reference-state plateau is caused by ~8 marginally-negative, near-rigid-body
translation/rotation mechanism modes — an **indefinite** assembled tangent, not a
clean drilling-rotation null space. Single-DOF-type pinning is therefore **not**
clearly indicated. The likely sources are geometric softening from the axial preload
and/or weak global restraint of near-rigid-body modes through the support / elastic-
link path.

## Allowed claim

- "the reference-state assembled tangent is indefinite with ~8 marginally-negative,
  translation/rotation (rigid-body-like) near-null modes distributed across DOF
  types; the plateau is not a clean single-mode drilling null space."

## Not claimed (preserved)

- NOT G1 closed, NOT 0.656 solved, NOT full-load nonlinear equilibrium closed,
  NOT material-Newton breadth closed. No pinning applied.

## Next slice (per F2g-alt taxonomy → Case B / C)

Because the near-null space is distributed rigid-body-like rather than a single
mechanism type, the next audit is **support / elastic-link restraint reconciliation**
(why do near-rigid-body modes carry near-zero / marginally-negative stiffness despite
the authored supports and elastic links?) — and, in parallel, the pragmatic
regularized continuation (F2h) using the small regularization that F2f showed makes
the operator factorable with a full-step direction. Pinning a single DOF type is not
the indicated path.
