# Cursor worker slice: Phase 1 core API contract freshness

Goal:
- Audit and refresh the Phase 1 core API contract evidence for the current working tree.

Scope:
- `scripts/build_phase1_core_api_contract_artifacts.py`
- `implementation/phase1/release_evidence/productization/phase1_core_api_contract_summary.json`
- `implementation/phase1/release_evidence/productization/phase1_core_api_sample_model.json`
- `implementation/phase1/release_evidence/productization/phase1_core_api_*`
- `src/structural_analysis/api/`
- `src/App.tsx`
- `tests/test_build_phase1_core_api_contract_artifacts.py`
- `tests/test_structural_analysis_core_api.py`

Questions to answer:
- Do the artifacts still check cleanly at the current HEAD?
- Do they prove the narrow path `load_model -> analyze(AnalysisConfig) -> validate` for Python API and CLI?
- Does the GUI consume stable result/report JSON rather than generated HTML for this slice?
- Are unsupported paths still visible without claiming full frame/shell/modal/buckling/nonlinear closure?

Constraints:
- Do not broaden solver claims.
- Do not mark Phase 1 complete unless the artifact and tests actually prove the full stated contract.
- Keep changes narrow and evidence-focused.

Verification:
- Run `python3 scripts/build_phase1_core_api_contract_artifacts.py --check`.
- Run focused pytest for the script and core API tests.
- Summarize changed files, tests, and remaining blockers.
