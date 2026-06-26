# Cursor Worker Task: Phase 2 Mesh/Load-Step Fallback Aggregation Audit

Goal:
Audit whether `build_phase2_mesh_load_step_convergence_artifacts.py` can hide per-step regularization/fallback evidence by reporting row/summary `regularization_used=false` and `fallback_used=false` as constants.

Scope:
- Read:
  - `/home/betelgeuze/.codex/attachments/98075342-506d-4368-9755-b528a830c410/goal-objective.md`
  - `.betelgeuze/intent_spec.md`
  - `.betelgeuze/project_contract.yaml`
  - `scripts/build_phase2_mesh_load_step_convergence_artifacts.py`
  - `tests/test_build_phase2_mesh_load_step_convergence_artifacts.py`
  - `src/structural_analysis/assembly/nonlinear_static.py`
  - `src/structural_analysis/solvers/nonlinear/newton.py`
- Candidate edit files, only if needed:
  - `scripts/build_phase2_mesh_load_step_convergence_artifacts.py`
  - `tests/test_build_phase2_mesh_load_step_convergence_artifacts.py`

Acceptance criteria:
- Row, result, and summary fallback/regularization flags must be derived from actual step/final metrics.
- A synthetic row containing step fallback or regularization must fail row aggregation rather than appear ready.
- Preserve existing claim boundaries: this remains a narrow 1D seed, not G1 closure.

Verification:
- Run focused tests for changed files.
- Summarize changed files, tests, and blockers only.
