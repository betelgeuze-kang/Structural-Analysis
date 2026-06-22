# OpenCode audit: Phase 2 linear reference artifact

Goal: audit the new Phase 2 linear reference slice for correctness and claim-boundary safety.

Scope:
- `src/structural_analysis/solvers/linear/static.py`
- `scripts/build_phase2_linear_reference_artifacts.py`
- `scripts/verify_quality_gate.py`
- `tests/test_build_phase2_linear_reference_artifacts.py`
- `tests/test_structural_analysis_core_api.py`
- generated `implementation/phase1/release_evidence/productization/phase2_linear_reference_*`

Check:
- The linear static result exposes residual as `F_internal - F_external`.
- The analytic axial bar result is physically correct and uses no regularization/fallback.
- The mechanism guard blocks a singular model instead of silently passing.
- The summary does not claim G1/full-mesh/full-load/material Newton/ROCm closure.
- `--check` mode detects stale artifacts.

Verification to run:
- `python3 scripts/build_phase2_linear_reference_artifacts.py --check`
- `python3 -m pytest -q tests/test_structural_analysis_core_api.py tests/test_build_phase2_linear_reference_artifacts.py`
- `python3 -m ruff check scripts/build_phase2_linear_reference_artifacts.py src/structural_analysis/solvers/linear/static.py tests/test_build_phase2_linear_reference_artifacts.py tests/test_structural_analysis_core_api.py scripts/verify_quality_gate.py`

Return only:
- changed files inspected
- test results
- failed test names, if any
- core findings or blockers
