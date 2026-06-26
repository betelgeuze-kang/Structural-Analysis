# Cursor Worker Task: Phase 2 Newton Regularization Contract Audit

Goal:
Audit whether the Phase 2 Newton/nonlinear seed can ever report a ready/pass result when regularization, fallback, singular tangent, or missing residual/increment gates are present.

Scope:
- Read:
  - `/home/betelgeuze/.codex/attachments/98075342-506d-4368-9755-b528a830c410/goal-objective.md`
  - `.betelgeuze/intent_spec.md`
  - `.betelgeuze/project_contract.yaml`
  - `src/structural_analysis/solvers/nonlinear/newton.py`
  - `src/structural_analysis/assembly/nonlinear_static.py`
  - `scripts/build_phase2_newton_globalization_artifacts.py`
  - `tests/test_build_phase2_newton_globalization_artifacts.py`
  - `tests/test_structural_analysis_core_api.py`
- Candidate edit files, only if needed:
  - `src/structural_analysis/solvers/nonlinear/newton.py`
  - `scripts/build_phase2_newton_globalization_artifacts.py`
  - `tests/test_build_phase2_newton_globalization_artifacts.py`
  - `tests/test_structural_analysis_core_api.py`

Acceptance criteria:
- No solver/evidence path may mark `ready`/`contract_pass=true` when regularization or fallback is used.
- Residual and increment gates must both be required.
- Singular tangent or unsupported backend must be visible as blocked/degraded with explicit unsupported feature or blocker.
- Do not broaden claims beyond scalar/vector axial Developer Preview seeds.

Verification:
- Run focused tests for changed files.
- Summarize changed files, tests, and blockers only.
