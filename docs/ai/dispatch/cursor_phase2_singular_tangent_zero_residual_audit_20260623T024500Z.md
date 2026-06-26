# Cursor Worker Task: Phase 2 Singular Tangent Zero-Residual Audit

Goal:
Audit whether scalar/vector Newton can report `ready` when tangent/Jacobian solve is singular but the residual gate is already satisfied.

Scope:
- Read:
  - `/home/betelgeuze/.codex/attachments/98075342-506d-4368-9755-b528a830c410/goal-objective.md`
  - `.betelgeuze/intent_spec.md`
  - `.betelgeuze/project_contract.yaml`
  - `src/structural_analysis/solvers/nonlinear/newton.py`
  - `scripts/build_phase2_newton_globalization_artifacts.py`
  - `tests/test_build_phase2_newton_globalization_artifacts.py`
- Candidate edit files, only if needed:
  - `src/structural_analysis/solvers/nonlinear/newton.py`
  - `scripts/build_phase2_newton_globalization_artifacts.py`
  - `tests/test_build_phase2_newton_globalization_artifacts.py`

Acceptance criteria:
- Singular tangent/Jacobian must not be converted to `ready` just because residual is zero.
- The blocked outcome must expose an explicit detail and unsupported feature.
- Normal scalar/vector seed solves must remain ready.
- Do not broaden claims beyond Phase 2 scalar/vector axial Developer Preview evidence.

Verification:
- Run focused tests for changed files.
- Summarize changed files, tests, and blockers only.
