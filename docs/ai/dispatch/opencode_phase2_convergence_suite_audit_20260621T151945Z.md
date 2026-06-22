# OpenCode audit: Phase 2 axial convergence suite

Goal: audit the Phase 2 linear reference convergence extension for correctness and claim-boundary safety.

Scope:
- `scripts/build_phase2_linear_reference_artifacts.py`
- `tests/test_build_phase2_linear_reference_artifacts.py`
- `src/structural_analysis/solvers/linear/static.py`
- generated `implementation/phase1/release_evidence/productization/phase2_linear_reference_convergence_suite.json`
- generated `implementation/phase1/release_evidence/productization/phase2_linear_reference_summary.json`

Check:
- The convergence suite runs multiple axial-chain mesh cases and a load-scaling case through the canonical API.
- Tip displacement, base reaction, residual, energy, fallback, and regularization fields are checked.
- The suite remains explicitly axial/small-reference only and does not claim full G1, full mesh/full load nonlinear, frame-shell-material, or production GPU/HIP closure.
- `--check` mode includes the convergence suite artifact and catches stale/missing outputs.

Verification to run:
- `python3 scripts/build_phase2_linear_reference_artifacts.py --check`
- `python3 -m pytest -q tests/test_build_phase2_linear_reference_artifacts.py tests/test_structural_analysis_core_api.py`
- `python3 -m ruff check scripts/build_phase2_linear_reference_artifacts.py tests/test_build_phase2_linear_reference_artifacts.py src/structural_analysis/solvers/linear/static.py`

Return only:
- changed files inspected
- test results
- failed test names, if any
- core findings or blockers
