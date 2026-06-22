# Cursor Worker Task: Phase 1 API Validation Contract Audit

Goal:
Audit the Phase 1 `load_model -> analyze(AnalysisConfig) -> validate` path for contract holes that could let mismatched reference comparisons pass while Developer Preview claim boundaries remain visible.

Scope:
- Read:
  - `/home/betelgeuze/.codex/attachments/98075342-506d-4368-9755-b528a830c410/goal-objective.md`
  - `.betelgeuze/intent_spec.md`
  - `.betelgeuze/project_contract.yaml`
  - `src/structural_analysis/api/core.py`
  - `src/structural_analysis/api/cli.py`
  - `scripts/build_phase1_core_api_contract_artifacts.py`
  - `tests/test_structural_analysis_core_api.py`
  - `tests/test_build_phase1_core_api_contract_artifacts.py`
- Candidate edit files, only if needed:
  - `src/structural_analysis/api/core.py`
  - `tests/test_structural_analysis_core_api.py`
  - `tests/test_build_phase1_core_api_contract_artifacts.py`

Acceptance criteria:
- `validate()` must not return `contract_pass=true` when supplied reference fields compare as `review`/mismatch.
- Unsupported features and blocked analysis states must remain blockers.
- Keep result schema and CLI/Python parity intact.
- Do not broaden solver claims beyond the current Developer Preview narrow paths.

Verification:
- Run focused API tests you change.
- Summarize changed files, tests, and blockers only.
