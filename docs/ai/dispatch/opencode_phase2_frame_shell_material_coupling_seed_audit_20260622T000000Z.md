# Goal
Audit the smallest aligned Phase 2 seed for `frame_shell_material_coupling_not_closed` without making broad G1/full-mesh claims.

# Scope
- Inspect:
  - `src/structural_analysis/assembly/`
  - `src/structural_analysis/solvers/nonlinear/newton.py`
  - `scripts/build_phase2_*`
  - `tests/test_build_phase2_*`
  - `tests/test_structural_analysis_core_api.py`
- Prefer a narrow deterministic artifact: shared global DOFs, one frame-like axial component, one shell/diaphragm-like coupling component, material tangent metadata, residual `F_internal-F_external`, finite-difference tangent check, no regularization/fallback false pass.
- Do not edit files.
- Do not claim G1/full-mesh/material closure.
- Do not read `.env*`, push, merge, deploy, or mutate remote state.

# Verification Criteria
- Identify candidate files to add or edit.
- Identify the smallest focused tests that would prove the seed.
- Identify claim-boundary wording and remaining blockers.

# Output
Return only:
- Changed files
- Test results
- Failed tests
- Core diff summary
- Blockers
