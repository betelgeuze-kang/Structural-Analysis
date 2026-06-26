# Goal
Add a narrow Phase 2 CPU sparse matrix backend seed for the canonical axial linear-static reference path without claiming G1/full production sparse closure.

# Scope
- Implement a deterministic sparse assembly/solve path for the existing axial/truss `linear_static` core API slice.
- Keep the dense path working and preserve all existing claim boundaries.
- Add or update Phase 2 artifacts so the sparse path has explicit evidence:
  - sparse stiffness storage/backend metadata
  - scipy sparse solve backend identity
  - dense-vs-sparse displacement/reaction/residual equivalence
  - no regularization or fallback false PASS
  - `g1_closure_claim=false`
  - remaining blockers still include full-mesh/full-load nonlinear equilibrium, frame/shell/material coupling, nonlinear convergence breadth, and production ROCm/HIP parity.

# Candidate files
- `src/structural_analysis/assembly/linear_static.py`
- `src/structural_analysis/solvers/linear/static.py`
- `scripts/build_phase2_linear_reference_artifacts.py`
- `tests/test_build_phase2_linear_reference_artifacts.py`
- add a focused helper/test file only if needed.

# Verification criteria
- `python3 scripts/build_phase2_linear_reference_artifacts.py --check`
- `python3 -m pytest -q tests/test_build_phase2_linear_reference_artifacts.py tests/test_structural_analysis_core_api.py`
- `python3 -m ruff check src/structural_analysis/assembly/linear_static.py src/structural_analysis/solvers/linear/static.py scripts/build_phase2_linear_reference_artifacts.py tests/test_build_phase2_linear_reference_artifacts.py`
- Do not update product readiness claims beyond honest generated artifact refreshes.
- Worker summary must list changed files, test commands/results, key diff points, and blockers only.
