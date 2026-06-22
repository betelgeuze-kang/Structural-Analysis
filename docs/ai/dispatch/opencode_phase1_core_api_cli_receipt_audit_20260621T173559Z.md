# OpenCode slice: Phase 1 core API CLI receipt audit

Goal: Audit the smallest evidence gap for proving Phase 1 `load_model -> analyze -> validate` works through both Python API and CLI, and is consumable by GUI.

Scope:
- Read only:
  - `src/structural_analysis/api/core.py`
  - `src/structural_analysis/api/cli.py`
  - `scripts/build_phase1_core_api_contract_artifacts.py`
  - `tests/test_build_phase1_core_api_contract_artifacts.py`
  - `tests/test_structural_analysis_core_api.py`
  - `src/App.tsx`
  - `tests/test_frontend_entry_shell.py`
- Do not edit files.

Question:
- The unit tests exercise the CLI, but do productization artifacts record CLI parity with the Python API and GUI schema?
- Identify the smallest missing receipt fields or focused tests to close that evidence gap without overstating general solver readiness.

Return only:
- Candidate files to edit.
- Missing/weak receipt fields.
- Suggested test names/commands.
- Blockers, if any.
