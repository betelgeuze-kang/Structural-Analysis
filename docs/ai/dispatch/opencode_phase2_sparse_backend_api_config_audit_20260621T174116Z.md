# OpenCode slice: Phase 2 sparse backend API config audit

Goal: Audit the smallest implementation/evidence gap for exposing the existing Phase 2 linear sparse backend through the canonical API/CLI config path.

Scope:
- Read only:
  - `src/structural_analysis/api/core.py`
  - `src/structural_analysis/api/cli.py`
  - `src/structural_analysis/solvers/linear/static.py`
  - `src/structural_analysis/assembly/linear_static.py`
  - `scripts/build_phase2_linear_reference_artifacts.py`
  - `tests/test_structural_analysis_core_api.py`
  - `tests/test_build_phase2_linear_reference_artifacts.py`
- Do not edit files.

Question:
- Sparse CSR assembly/solve already exists, but is it selectable via `AnalysisConfig` and CLI, and does Phase 2 evidence prove that route?
- Identify the smallest fields/tests/artifact changes needed to connect sparse backend to the canonical API without overstating general solver closure.

Return only:
- Candidate files to edit.
- Missing/weak API/config/evidence fields.
- Suggested test names/commands.
- Blockers, if any.
