# Cursor worker task: Phase 0 Developer Preview scope parity

Goal:
Strengthen the Phase 0 evidence that Developer Preview scope/exclusions are aligned across README, GUI, and report surfaces without promoting Developer Preview or Commercial Release readiness.

Scope:
- `scripts/build_developer_preview_readiness.py`
- `tests/test_build_developer_preview_readiness.py`
- Existing generated artifacts under `implementation/phase1/release_evidence/productization/`
- `README.md`
- `docs/commercialization-gap-current-state.md`
- `src/App.tsx`

Requested implementation direction:
- Keep the existing `scope_boundary_sync` contract, but make the surfaces explicit:
  - README surface
  - report/current-state surface
  - GUI surface
- Preserve checks for included scope anchors, excluded scope anchors, future Commercial Release blockers, and GUI consumption of generated readiness scope.
- If useful, include generated Developer Preview report markdown as an additional report surface only if this avoids circular generation drift.
- Do not claim Developer Preview ready or Commercial Release ready.

Verification criteria:
- Focused tests pass.
- `developer_preview_readiness.json` remains blocked with current blockers.
- `scope_boundary_sync.contract_pass` remains true only if README, report, and GUI surfaces all expose the required boundary.
- Report changed files, tests run, and remaining blockers concisely.
