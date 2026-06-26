# OpenCode slice: Developer Preview scope sync audit

Goal: Audit whether the Phase 0 Developer Preview scope/exclusion boundary is machine-checked across README, GUI, and the generated Developer Preview report.

Scope:
- Read only these candidate areas unless needed for targeted references:
  - `README.md`
  - `docs/commercialization-gap-current-state.md`
  - `scripts/build_developer_preview_readiness.py`
  - `tests/test_build_developer_preview_readiness.py`
  - `src/App.tsx`
  - frontend/readiness sync tests under `tests/`
- Do not edit files.

Question:
- Identify the smallest missing assertion or receipt field that would make the Phase 0 completion condition stronger: Developer Preview scope and exclusions are consistently visible in README, GUI, and report.

Return only:
- Candidate files to edit.
- Missing/weak assertions.
- Suggested focused test names/commands.
- Blockers, if any.
